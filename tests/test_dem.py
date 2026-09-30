from dataclasses import replace

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from waterlagen import _geopandas as wgpd
from waterlagen.ahn import interpolate
from waterlagen.dem import DemConfig, bouw_dem_tiles
from waterlagen.dem.gebouwen import calculate_building_elevations
from waterlagen.functioneel_landgebruik import landgebruik_berekenen as landuse
from waterlagen.functioneel_landgebruik.gebouwen import (
    building_paths,
    ensure_building_index,
)
from waterlagen.raster.config import RasterOutputConfig
from waterlagen.raster.vrt import create_cog_file, create_vrt_file


def write_ahn(path, data, *, scale=1.0, offset=0.0):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype=data.dtype,
        nodata=-9999,
        crs=28992,
        transform=from_origin(0, data.shape[0], 1, 1),
    ) as dst:
        dst.write(data, 1)
        dst.scales, dst.offsets = (scale,), (offset,)
    return path


def read(path):
    with rasterio.open(path) as src:
        return src.read(1)


@pytest.fixture
def landuse_inputs(tmp_path, monkeypatch):
    # ID 1 crosses the four-tile junction; IDs 2 and 3 touch each other.
    buildings = gpd.GeoDataFrame(
        {
            "identificatie": [
                "0000000000000001",
                "9999999999999999",
                "9999999999999998",
            ],
            "code": [20, 20, 0],
            "source_code": [10, 10, 10],
        },
        geometry=[
            box(29.1, 29.1, 34.9, 34.9),
            box(8.1, 8.1, 11.9, 11.9),
            box(11.9, 8.1, 15.9, 11.9),
        ],
        crs=28992,
    )
    source = tmp_path / "bag.gpkg"
    buildings.to_file(source, layer="pand")
    index = ensure_building_index(source, tmp_path / "gebouw_index.sqlite")
    ground = gpd.GeoDataFrame(
        {"code": [78], "source_code": [2]}, geometry=[box(0, 0, 64, 64)], crs=28992
    )
    water = gpd.GeoDataFrame(
        {"code": [100], "source_code": [12]}, geometry=[box(30, 30, 31, 31)], crs=28992
    )
    monkeypatch.setattr(landuse, "_validate_sources_exist", lambda *args: None)
    monkeypatch.setattr(
        landuse, "_read_buitendijks_area", lambda *args: box(100, 100, 101, 101)
    )
    monkeypatch.setattr(
        landuse,
        "_prepare_priority_sources",
        lambda *args, **kwargs: [ground, buildings, water],
    )
    tiles = []
    for y in (0, 32):
        for x in (0, 32):
            tile = tmp_path / "landuse" / f"tile_{x}_{y}.tif"
            landuse.bouw_functioneel_landgebruik(
                tile,
                bounds=(x, y, x + 32, y + 32),
                resolution_m=1,
                gap_fill_distance_m=0,
                download_missing=False,
                building_index_path=index,
                output_config=RasterOutputConfig(block_size=16, overview_factors=(2,)),
            )
            tiles.append(tile)
    return tiles


def test_building_ids_exact_and_separate(landuse_inputs):
    all_ids = set()
    for tile in landuse_inputs:
        ids_path, footprints = building_paths(tile)
        ids = read(ids_path)
        np.testing.assert_array_equal(
            ids > 0, read(tile.parent / "bronnen" / tile.name) == 10
        )
        all_ids.update(np.unique(ids))
        table = wgpd.read_file(footprints)
        assert "9999999999999999" in set(table.identificatie)
        assert "9999999999999998" in set(table.identificatie)
    assert all_ids == {0, 1, 2, 3}


def test_dem_pipeline_provenance_precedence_cogs_and_resume(
    tmp_path, landuse_inputs, monkeypatch
):
    data = np.full((64, 64), 100, dtype="int16")
    data[:, 32:] = 200  # Different donors on either side of the crossing building.
    data[28:36, 28:36] = -9999  # Crossing building samples original surrounding AHN.
    data[45:64, 0:23] = -9999  # Both touching buildings unresolved at 5 m.
    data[4, 31:34] = -9999  # AHN hole crosses a tile edge.
    ahn = write_ahn(tmp_path / "ahn.tif", data, scale=0.01, offset=2.0)
    config = DemConfig(
        interpolation_max_distance_m=2,
        output=RasterOutputConfig(block_size=16, overview_factors=(2,)),
    )
    calls = []
    actual = interpolate.interpolate_masked

    def spy(*args, **kwargs):
        calls.append(kwargs.get("method", "inverse_distance"))
        return actual(*args, **kwargs)

    monkeypatch.setattr(interpolate, "interpolate_masked", spy)
    result = bouw_dem_tiles(
        tmp_path / "dem", ahn_vrt_path=ahn, landuse_tiles=landuse_inputs, config=config
    )
    assert calls == ["inverse_distance"] * 4
    dem, provenance = read(result), read(result.parent / "dem_bron.tif")
    assert set(np.unique(provenance)) == {0, 1, 2, 3}
    np.testing.assert_array_equal(dem[provenance == 1], data[provenance == 1])
    assert np.all(dem[provenance == 2] == 200)
    assert np.all(dem[provenance == 0] == -9999)
    assert np.all(provenance[4, 31:34] == 3)
    for name in ("dem", "dem_bron"):
        np.testing.assert_array_equal(
            read(result.parent / f"{name}.vrt"), read(result.parent / f"{name}.tif")
        )
    heights = wgpd.read_file(result.parent / "gebouwhoogten.gpkg")
    assert heights.loc[heights.gebouw_id == 1, "hoogte_m"].iloc[0] == 4.0
    diagnostics = wgpd.read_file(result.parent / "nodata.gpkg", layer="nodata")
    unresolved = diagnostics[diagnostics.bron == "Gebouw"]
    assert set(unresolved.identificatie) == {"9999999999999999", "9999999999999998"}
    assert unresolved.zoekafstand_m.eq(5).all()
    assert unresolved.geometry.notna().all()
    # Every piece of the crossing building receives the same stored value.
    for tile in landuse_inputs:
        ids = read(building_paths(tile)[0])
        assert np.all(
            read(result.parent / "tiles" / "gebouwen" / tile.name)[ids == 1] == 200
        )
    before = (result.parent / "gebouwhoogten.gpkg").stat().st_mtime_ns
    calls.clear()
    bouw_dem_tiles(
        result.parent, ahn_vrt_path=ahn, landuse_tiles=landuse_inputs, config=config
    )
    assert calls == []
    assert (result.parent / "gebouwhoogten.gpkg").stat().st_mtime_ns == before
    (result.parent / "tiles" / "gebouwen" / landuse_inputs[0].name).unlink()
    bouw_dem_tiles(
        result.parent, ahn_vrt_path=ahn, landuse_tiles=landuse_inputs, config=config
    )
    assert calls == ["inverse_distance"]
    with pytest.raises(ValueError, match="configuration changed"):
        bouw_dem_tiles(
            result.parent,
            ahn_vrt_path=ahn,
            landuse_tiles=landuse_inputs,
            config=replace(config, building_percentile=80),
        )


def test_iterative_search_limit_percentile_and_neighbour_exclusion(tmp_path):
    data = np.full((24, 24), -9999, dtype="float32")
    # Building at x/y 10..12; neighbouring building contains tempting false donors.
    data[12:14, 12:14] = 999
    data[12, 7] = 10  # x=7.5, y=11.5: first valid at radius 3.
    data[13, 7] = 30
    buildings = gpd.GeoDataFrame(
        {"gebouw_id": [1, 2], "identificatie": ["a", "b"]},
        geometry=[box(10, 10, 12, 12), box(12, 10, 14, 12)],
        crs=28992,
    )
    ahn = write_ahn(tmp_path / "sample.tif", data)
    with rasterio.open(ahn) as source:
        heights = calculate_building_elevations(buildings, {1}, source, DemConfig())
        assert heights.hoogte_m.iloc[0] == 25
        assert heights.zoekafstand_m.iloc[0] == 3
        assert heights.donor_aantal.iloc[0] == 2
        limited = calculate_building_elevations(
            buildings, {1}, source, DemConfig(building_max_search_distance_m=2)
        )
        assert limited.hoogte_m.isna().all()
        assert limited.zoekafstand_m.iloc[0] == 2
    data[:] = -9999
    data[12, 4] = 50  # 5.5 m away; default maximum is 5, not 6.
    write_ahn(ahn, data)
    with rasterio.open(ahn) as source:
        assert (
            calculate_building_elevations(buildings, {1}, source, DemConfig())
            .hoogte_m.isna()
            .all()
        )


def test_excludes_neighbour_touching_donor_pixel_outside_search_ring(tmp_path):
    data = np.full((24, 24), -9999, dtype="float32")
    data[12, 9] = 10
    data[11, 12] = 999
    building = box(10, 10, 12, 12)
    neighbour = box(12.9, 12.9, 13.1, 13.1)
    assert not neighbour.intersects(building.buffer(1))
    buildings = gpd.GeoDataFrame(
        {"gebouw_id": [1, 2], "identificatie": ["a", "b"]},
        geometry=[building, neighbour],
        crs=28992,
    )
    ahn = write_ahn(tmp_path / "corner.tif", data)
    with rasterio.open(ahn) as source:
        heights = calculate_building_elevations(buildings, {1}, source, DemConfig())
    # Its geometry misses the ring, but all_touched marks the candidate pixel.
    assert heights.hoogte_m.iloc[0] == 10
    assert heights.donor_aantal.iloc[0] == 1


def test_shared_interpolation_keeps_masks_and_uses_metres():
    data = np.full((5, 9), -9999, dtype="float32")
    data[2, 0] = 10
    targets = data == -9999
    targets[:, 5:] = False
    result = interpolate.interpolate_masked(
        data,
        target_mask=targets,
        donor_mask=data != -9999,
        max_distance_m=2,
        pixel_width=0.5,
        pixel_height=0.5,
    )
    assert result.values[2, 4] == 10
    assert result.values[2, 5] == -9999
    assert not result.filled_mask[:, 5:].any()
    assert result.values[2, 0] == data[2, 0]


def test_dem_donor_only_in_neighbouring_tile(tmp_path, landuse_inputs):
    data = np.full((64, 64), 10, dtype="float32")
    data[:, :32] = -9999
    ahn = write_ahn(tmp_path / "edge.tif", data)
    config = DemConfig(interpolation_max_distance_m=2)
    result = bouw_dem_tiles(
        tmp_path / "edge_dem",
        ahn_vrt_path=ahn,
        landuse_tiles=landuse_inputs,
        config=config,
    )
    values = read(result)
    provenance = read(result.parent / "dem_bron.tif")
    assert values[5, 31] == 10  # No original donor anywhere in the left tile.
    assert provenance[5, 31] == 3
    assert provenance[5, 28] == 0
    whole = interpolate.interpolate_masked(
        data,
        target_mask=data == -9999,
        donor_mask=data != -9999,
        max_distance_m=2,
        pixel_width=1,
        pixel_height=1,
    )
    np.testing.assert_array_equal(
        values[provenance == 3], whole.values[provenance == 3]
    )


def test_landuse_calls_same_helper(monkeypatch):
    from waterlagen.functioneel_landgebruik.aanvullen import _fill_gaps

    calls = []
    actual = interpolate.interpolate_masked

    def spy(*args, **kwargs):
        calls.append(kwargs["method"])
        return actual(*args, **kwargs)

    monkeypatch.setattr(interpolate, "interpolate_masked", spy)
    values = np.array([[78, 0, 0]], dtype="uint8")
    sources = np.array([[2, 0, 0]], dtype="uint8")
    assert (
        _fill_gaps(
            values,
            sources,
            np.array([[False, True, False]]),
            radius_m=2,
            pixel_width=1,
            pixel_height=1,
        )
        == 1
    )
    assert calls == ["nearest"]
    assert values.tolist() == [[78, 78, 0]]


def test_explicit_vrt_priority(tmp_path):
    base = write_ahn(tmp_path / "base.tif", np.full((8, 8), 10, dtype="int16"))
    data = np.full((8, 8), -9999, dtype="int16")
    data[3, 3] = 20
    buildings = write_ahn(tmp_path / "buildings.tif", data)
    vrt = create_vrt_file(tmp_path / "dem.vrt", files=[base, buildings])
    assert read(vrt)[3, 3] == 20
    assert read(vrt)[0, 0] == 10


def test_cog_preserves_nan_nodata_scale_and_offset(tmp_path):
    path = write_ahn(
        tmp_path / "float.tif",
        np.full((32, 32), 10, dtype="float32"),
        scale=0.01,
        offset=2.5,
    )
    with rasterio.open(path, "r+") as dst:
        dst.nodata = float("nan")
    vrt = create_vrt_file(tmp_path / "float.vrt", files=[path])
    cog = create_cog_file(
        vrt, tmp_path / "cog.tif", show_progress=False, overview_resampling="average"
    )
    with rasterio.open(cog) as src:
        assert np.isnan(src.nodata)
        assert src.scales == (0.01,)
        assert src.offsets == (2.5,)


def test_rejects_insufficient_prepared_building_context(tmp_path, landuse_inputs):
    ahn = write_ahn(tmp_path / "ahn.tif", np.ones((64, 64), dtype="float32"))
    with pytest.raises(ValueError, match="neighbour context"):
        bouw_dem_tiles(
            tmp_path / "context",
            ahn_vrt_path=ahn,
            landuse_tiles=landuse_inputs,
            config=DemConfig(building_max_search_distance_m=10),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"building_max_search_distance_m": 0},
        {"building_buffer_step_m": 0},
        {"building_percentile": 101},
        {"interpolation_max_distance_m": float("nan")},
    ],
)
def test_dem_config_validation(kwargs):
    with pytest.raises(ValueError):
        DemConfig(**kwargs)
