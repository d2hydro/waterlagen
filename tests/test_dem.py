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
from waterlagen.dem.productie import _tile_paths
from waterlagen.functioneel_landgebruik import landgebruik_berekenen as landuse
from waterlagen.functioneel_landgebruik.gebouwen import (
    building_paths,
    ensure_building_index,
)
from waterlagen.raster.config import RasterOutputConfig
from waterlagen.raster.vrt import create_cog_file, create_vrt_file


@pytest.fixture(autouse=True)
def default_dem_workers(monkeypatch):
    from waterlagen.settings import settings

    monkeypatch.setattr(settings, "dem_workers", 1)
    monkeypatch.setattr(settings, "dem_building_workers", 1)


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
    data[53:56, 9:15] = 100  # Original AHN under failed buildings must survive.
    ahn = write_ahn(tmp_path / "ahn.tif", data, scale=0.01, offset=2.0)
    config = DemConfig(
        interpolation_max_distance_m=32,
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
    assert set(np.unique(provenance)) == {1, 2, 3}
    assert np.all(dem != -9999)
    ahn_provenance = read(result.parent / "ahn_bron.tif")
    assert np.all(ahn_provenance[data != -9999] == 1)
    assert np.all(ahn_provenance[data == -9999] == 3)
    np.testing.assert_array_equal(dem[provenance == 1], data[provenance == 1])
    assert np.all(dem[provenance == 2] == 200)
    assert np.all(dem[provenance == 0] == -9999)
    assert np.all(provenance[4, 31:34] == 3)
    for name in ("dem", "dem_bron", "ahn_bron"):
        np.testing.assert_array_equal(
            read(result.parent / f"{name}.vrt"), read(result.parent / f"{name}.tif")
        )
    heights = wgpd.read_file(result.parent / "gebouwhoogten.gpkg")
    assert heights.loc[heights.gebouw_id == 1, "hoogte_m"].iloc[0] == 4.0
    diagnostics = wgpd.read_file(result.parent / "nodata.gpkg", layer="nodata")
    unresolved = diagnostics[diagnostics.bron == "Gebouw"]
    assert unresolved.categorie.eq("Gebouw").all()
    assert set(unresolved.identificatie) == {"9999999999999999", "9999999999999998"}
    assert unresolved.zoekafstand_m.eq(5).all()
    assert unresolved.geometry.notna().all()
    # Failed buildings retain terrain provenance and are still diagnosed per tile.
    for tile in landuse_inputs:
        ids = read(building_paths(tile)[0])
        products = _tile_paths(result.parent, tile)
        failed = np.isin(ids, [2, 3])
        np.testing.assert_array_equal(
            read(products.provenance)[failed], read(products.ahn_provenance)[failed]
        )
        local = wgpd.read_file(products.diagnostics, layer="nodata")
        assert set(local.loc[local.bron == "Gebouw", "gebouw_id"]) == set(
            np.unique(ids[failed])
        )
    # Every piece of the crossing building receives the same stored value.
    for tile in landuse_inputs:
        ids = read(building_paths(tile)[0])
        assert np.all(read(_tile_paths(result.parent, tile).buildings)[ids == 1] == 200)
    before = (result.parent / "gebouwhoogten.gpkg").stat().st_mtime_ns
    calls.clear()
    bouw_dem_tiles(
        result.parent, ahn_vrt_path=ahn, landuse_tiles=landuse_inputs, config=config
    )
    assert calls == []
    assert (result.parent / "gebouwhoogten.gpkg").stat().st_mtime_ns == before
    _tile_paths(result.parent, landuse_inputs[0]).buildings.unlink()
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
    output = tmp_path / "edge_dem"
    bouw_dem_tiles(
        output, ahn_vrt_path=ahn, landuse_tiles=landuse_inputs, config=config
    )
    assert (output / "dem.tif").exists()
    assert (output / "dem.vrt").exists()
    assert (output / "dem_complete.json").exists()
    assert (output / "nodata.gpkg").is_file()
    # Upper left core has no donor itself; the right neighbour supplies its edge.
    tile_paths = _tile_paths(output, landuse_inputs[2])
    values = read(tile_paths.terrain)
    provenance = read(tile_paths.ahn_provenance)
    assert values[5, 31] == 10
    assert provenance[5, 31] == 3
    assert provenance[5, 29] == 0  # Three metres exceeds the hard two-metre limit.
    whole = interpolate.interpolate_masked(
        data,
        target_mask=data == -9999,
        donor_mask=data != -9999,
        max_distance_m=2,
        pixel_width=1,
        pixel_height=1,
    )
    np.testing.assert_array_equal(values, whole.values[:32, :32])


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


def test_parallel_tiles_match_sequential_and_resume_with_different_workers(
    tmp_path, landuse_inputs
):
    data = np.full((64, 64), 100, dtype="float32")
    data[3:7, 30:34] = -9999
    ahn = write_ahn(tmp_path / "parallel_ahn.tif", data)
    config = DemConfig(interpolation_max_distance_m=3)
    serial = bouw_dem_tiles(
        tmp_path / "serial",
        ahn_vrt_path=ahn,
        landuse_tiles=landuse_inputs,
        config=config,
        workers=1,
    )
    parallel = bouw_dem_tiles(
        tmp_path / "parallel",
        ahn_vrt_path=ahn,
        landuse_tiles=landuse_inputs,
        config=config,
        workers=2,
        building_workers=2,
    )
    for name in ("dem.tif", "dem_bron.tif", "ahn_bron.tif"):
        np.testing.assert_array_equal(
            read(serial.parent / name), read(parallel.parent / name)
        )
    before = parallel.stat().st_mtime_ns
    bouw_dem_tiles(
        parallel.parent,
        ahn_vrt_path=ahn,
        landuse_tiles=landuse_inputs,
        config=config,
        workers=1,
    )
    assert parallel.stat().st_mtime_ns == before


@pytest.fixture
def height_batches(tmp_path, landuse_inputs, monkeypatch):
    import waterlagen.dem.productie as production

    buildings = gpd.GeoDataFrame(
        {"gebouw_id": [1, 2, 3], "identificatie": ["a", "b", "c"]},
        geometry=[box(30, 30, 34, 34), box(8, 8, 10, 10), box(40, 8, 42, 10)],
        crs=28992,
    )
    selected = [{1, 2}, {1, 3}, {1}, {1}]
    selection = dict(zip(landuse_inputs, selected, strict=True))
    monkeypatch.setattr(
        production,
        "_read_buildings",
        lambda tiles, context_m: (buildings.copy(), selection[tiles[0]]),
    )
    values = np.indices((64, 64)).sum(axis=0).astype("float32")
    # The shared building needs multiple search-buffer iterations.
    values[28:36, 28:36] = -9999
    ahn = write_ahn(tmp_path / "batch_ahn.tif", values)
    return landuse_inputs, ahn


def test_height_batches_parallel_match_serial_and_assign_ids_once(
    tmp_path, height_batches
):
    import pandas as pd

    from waterlagen.dem.productie import _prepare_heights

    tiles, ahn = height_batches
    outputs = []
    for workers in (1, 2):
        folder = tmp_path / f"heights_{workers}"
        folder.mkdir()
        target = folder / "gebouwhoogten.gpkg"
        with rasterio.open(ahn) as source:
            _prepare_heights(tiles, source, target, DemConfig(), False, workers)
        outputs.append(
            wgpd.read_file(target).sort_values("gebouw_id").reset_index(drop=True)
        )
        batches = [
            wgpd.read_file(p) for p in (folder / "gebouwhoogten_batches").glob("*.gpkg")
        ]
        assert len(batches) == 2
        ids = pd.concat(batches).gebouw_id
        assert ids.is_unique
        assert set(ids) == {1, 2, 3}
    pd.testing.assert_frame_equal(outputs[0], outputs[1])
    assert outputs[1].loc[outputs[1].gebouw_id == 1, "zoekafstand_m"].iloc[0] > 1


def test_height_batches_resume_after_merge_failure(
    tmp_path, height_batches, monkeypatch
):
    import json

    import waterlagen.dem.productie as production

    tiles, ahn = height_batches
    target = tmp_path / "gebouwhoogten.gpkg"
    original = production._append_heights
    calls = 0

    def fail_second_append(path, heights):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("interrupted merge")
        return original(path, heights)

    monkeypatch.setattr(production, "_append_heights", fail_second_append)
    with (
        rasterio.open(ahn) as source,
        pytest.raises(OSError, match="interrupted merge"),
    ):
        production._prepare_heights(tiles, source, target, DemConfig(), False)
    assert target.with_suffix(".tmp.gpkg").exists()
    assert not target.exists()
    monkeypatch.setattr(production, "_append_heights", original)

    def no_recalculation(*args, **kwargs):
        raise AssertionError("Completed batches must be reused")

    monkeypatch.setattr(production, "calculate_building_elevations", no_recalculation)
    with rasterio.open(ahn) as source:
        production._prepare_heights(tiles, source, target, DemConfig(), False)
    heights = wgpd.read_file(target)
    assert set(heights.gebouw_id) == {1, 2, 3}
    assert heights.gebouw_id.is_unique
    status = json.loads((tmp_path / "gebouwhoogten_status.json").read_text())
    assert status["stage"] == "complete"
    assert status["completed_tiles"] == status["total_tiles"] == 4
    assert status["completed_buildings"] == 3


@pytest.mark.parametrize("recovery", [False, True])
def test_height_batches_reuse_legacy_partial_table(
    tmp_path, height_batches, monkeypatch, recovery
):
    import waterlagen.dem.productie as production

    tiles, ahn = height_batches
    target = tmp_path / "gebouwhoogten.gpkg"
    buildings, _ = production._read_buildings([tiles[0]], 5)
    with rasterio.open(ahn) as source:
        cached = calculate_building_elevations(buildings, {1, 2}, source, DemConfig())
    suffix = ".resume.gpkg" if recovery else ".tmp.gpkg"
    cached.to_file(target.with_suffix(suffix), layer="gebouwen")
    original = production.calculate_building_elevations
    sampled = []

    def track(buildings, ids, ahn, config):
        sampled.extend(ids)
        return original(buildings, ids, ahn, config)

    monkeypatch.setattr(production, "calculate_building_elevations", track)
    with rasterio.open(ahn) as source:
        production._prepare_heights(tiles, source, target, DemConfig(), False)
    assert sampled == [3]
    heights = wgpd.read_file(target).set_index("gebouw_id")
    np.testing.assert_array_equal(heights.loc[[1, 2], "hoogte_m"], cached.hoogte_m)


@pytest.mark.parametrize("nested", [False, True])
def test_landuse_run_validation_checks_real_companions(
    tmp_path, landuse_inputs, monkeypatch, nested
):
    import hashlib
    import json
    import shutil

    from waterlagen.areas import Area
    from waterlagen.dem import inputs

    run = tmp_path / "landuse_run"
    shutil.copytree(landuse_inputs[0].parent, run / "tiles")
    rows = []
    for tile in landuse_inputs:
        with rasterio.open(tile) as src:
            x, y, xmax, ymax = map(int, src.bounds)
        rows.append(
            {
                "tile_id": tile.stem,
                "column": x // 32,
                "row": y // 32,
                "xmin": x,
                "ymin": y,
                "xmax": xmax,
                "ymax": ymax,
                "geometry": box(x, y, xmax, ymax),
            }
        )
    gpd.GeoDataFrame(rows, crs=28992).to_file(run / "tiles.gpkg", layer="tiles")
    (run / "landgebruik_met_code.csv").write_bytes(b"test mapping")
    (run / "run.json").write_text(
        json.dumps(
            {
                "dataset": "functioneel_landgebruik",
                "created": "2026-01-01T00:00:00+00:00",
                "scope": "nederland",
                "status": "complete",
                "parameters": {
                    "resolution_m": 1,
                    "csv_sha256": hashlib.sha256(b"test mapping").hexdigest(),
                },
            }
        )
    )
    monkeypatch.setattr(inputs, "tile_filename", lambda _, tile: f"{tile.tile_id}.tif")
    if nested:
        from waterlagen.functioneel_landgebruik.paths import source_path

        for original in landuse_inputs:
            old = run / "tiles" / original.name
            new = run / "tiles" / original.stem / "functioneel_landgebruik.tif"
            new.parent.mkdir()
            for src, dst in zip(
                [source_path(old), *building_paths(old), old],
                [source_path(new), *building_paths(new), new],
                strict=True,
            ):
                src.rename(dst)
        metadata_path = run / "run.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["parameters"]["tile_layout_version"] = 2
        metadata_path.write_text(json.dumps(metadata))
    selected = inputs.validate_landuse_run(run, Area.nederland, 5)
    assert len(selected.paths) == 4
    # Exercise the default Nederland entry point and its pinned resume metadata
    # on small real rasters; no national data or network access is involved.
    from types import SimpleNamespace

    from waterlagen.dem import workflow as script

    gpd.GeoDataFrame(rows, crs=28992).to_file(run / "grid.gpkg", layer="tiles")
    boundary_dir = tmp_path / "boundaries"
    boundary_dir.mkdir()
    gpd.GeoDataFrame(geometry=[box(0, 0, 64, 64)], crs=28992).to_file(
        boundary_dir / "BestuurlijkeGebieden_2026.gpkg", layer="landgebied"
    )
    store = SimpleNamespace(
        processed_data_dir=tmp_path / "processed",
        administratieve_gebieden_dir=boundary_dir,
    )
    ahn = write_ahn(tmp_path / "entry_ahn.tif", np.ones((64, 64), dtype="float32"))
    result = script.main(
        data_store=store, landuse_run=run, ahn_vrt=ahn, workers=1, run_id="entry"
    )
    assert (
        result == store.processed_data_dir / "dem" / "nederland" / "entry" / "dem.tif"
    )
    modified = result.stat().st_mtime_ns
    script.main(
        data_store=store,
        landuse_run=run,
        ahn_vrt=ahn,
        workers=2,
        run_id="entry",
        resume=True,
    )
    assert result.stat().st_mtime_ns == modified
    metadata = json.loads((result.parent / "run.json").read_text())
    assert metadata["workers"] == 2
    assert metadata["landuse_dependency"]["path"] == str(run.resolve())
    with pytest.raises(ValueError, match="neighbour context"):
        inputs.validate_landuse_run(run, Area.nederland, 6)
    with rasterio.open(building_paths(selected.paths[0])[0], "r+") as ids:
        values = ids.read(1)
        values[0, 0] = 42
        ids.write(values, 1)
    with pytest.raises(ValueError, match="source code 10"):
        inputs.validate_landuse_run(run, Area.nederland, 5)


def test_dem_only_requires_coverage_inside_selected_cores(tmp_path, landuse_inputs):
    ahn = write_ahn(tmp_path / "ahn.tif", np.ones((64, 64), dtype="float32"))
    selected = [landuse_inputs[0], landuse_inputs[3]]
    result = bouw_dem_tiles(
        tmp_path / "diagonal", ahn_vrt_path=ahn, landuse_tiles=selected
    )
    with rasterio.open(result) as source:
        missing = np.ma.getmaskarray(source.read(1, masked=True))
    assert missing[:32, :32].all()
    assert missing[32:, 32:].all()
    assert not missing[:32, 32:].any()
    assert not missing[32:, :32].any()
    for tile in selected:
        folder = _tile_paths(result.parent, tile).terrain.parent
        assert (folder / "workflow.log").is_file()
        assert (folder / "status.json").is_file()
        assert (folder / "nodata.gpkg").is_file()


def test_coverage_counts_water_outside_and_unknown_landuse(tmp_path):
    from waterlagen.dem.productie import DemTilePaths, _check_coverage

    missing = np.full((4, 4), -9999, dtype="float32")
    terrain = write_ahn(tmp_path / "terrain.tif", missing)
    overlay = missing.copy()
    overlay[0, 0] = 12
    buildings = write_ahn(tmp_path / "buildings.tif", overlay)
    classes = np.full((4, 4), 78, dtype="int16")
    classes[1, 0], classes[2, 0], classes[3, 0] = 100, 228, 0
    landuse = write_ahn(tmp_path / "landuse.tif", classes)
    boundary = tmp_path / "boundary.gpkg"
    gpd.GeoDataFrame(geometry=[box(0, 0, 1.6, 4)], crs=28992).to_file(
        boundary, layer="landgebied"
    )
    paths = DemTilePaths(terrain, buildings, terrain, terrain, terrain)
    counts = _check_coverage([paths], [landuse], boundary)
    assert counts.outside_landgebied == 8
    assert counts.open_water == 2
    assert counts.inside_landgebied_nonwater == 5  # Includes the unknown class 0.
    counts = _check_coverage([paths], [landuse], None)
    assert counts.outside_landgebied == 0
    assert counts.inside_landgebied_nonwater == 13


def test_diagnostics_split_ahn_gaps_before_building_overlay(tmp_path, landuse_inputs):
    from rasterio.features import rasterize

    data = np.full((64, 64), 10, dtype="float32")
    data[:2, :3] = -9999
    data[32, 32] = -9999  # Valid building height will cover this AHN gap.
    ahn = write_ahn(tmp_path / "categories_ahn.tif", data)
    with rasterio.open(landuse_inputs[2], "r+") as landuse_raster:
        values = landuse_raster.read(1)
        values[:2, :3] = 78
        values[0, :3] = [100, 228, 0]
        landuse_raster.write(values, 1)
    result = bouw_dem_tiles(
        tmp_path / "categories",
        ahn_vrt_path=ahn,
        landuse_tiles=landuse_inputs,
        config=DemConfig(interpolation_max_distance_m=0),
    )
    diagnostics = wgpd.read_file(result.parent / "nodata.gpkg", layer="nodata")
    ahn_gaps = diagnostics[diagnostics.bron == "AHN"]
    assert ahn_gaps.groupby("categorie").geometry.apply(
        lambda s: s.area.sum()
    ).to_dict() == {
        "AHN_water": 2.0,
        "AHN_overig": 5.0,
    }
    with rasterio.open(result) as raster:
        categories = rasterize(
            [
                (row.geometry, 1 if row.categorie == "AHN_water" else 2)
                for row in ahn_gaps.itertuples()
            ],
            out_shape=raster.shape,
            transform=raster.transform,
        )
    assert categories[0, :3].tolist() == [1, 1, 2]
    assert categories[1, :3].tolist() == [2, 2, 2]
    assert categories[32, 32] == 2
    assert read(result)[32, 32] == 10
    missing = read(result) == -9999
    assert missing.sum() == 6
    np.testing.assert_array_equal(
        missing, np.isnan(read(result.parent / "dem_float.tif"))
    )


def test_new_coverage_policy_reuses_unpublished_legacy_tiles(
    tmp_path, landuse_inputs, monkeypatch
):
    import json

    import waterlagen.dem.productie as production

    data = np.full((64, 64), 10, dtype="float32")
    data[:, :32] = -9999
    ahn = write_ahn(tmp_path / "coverage_ahn.tif", data)
    output = tmp_path / "coverage_dem"
    config = DemConfig(interpolation_max_distance_m=2)
    original_cog = production.create_cog_file

    def fail_export(*args, **kwargs):
        raise RuntimeError("Interrupted before export")

    monkeypatch.setattr(production, "create_cog_file", fail_export)
    with pytest.raises(RuntimeError, match="Interrupted before export"):
        bouw_dem_tiles(
            output, ahn_vrt_path=ahn, landuse_tiles=landuse_inputs, config=config
        )
    monkeypatch.setattr(production, "create_cog_file", original_cog)
    # Simulate the previous diagnostic schema without invalidating tile rasters.
    for tile in landuse_inputs:
        paths = _tile_paths(output, tile)
        legacy = wgpd.read_file(paths.diagnostics).drop(columns="categorie")
        legacy.to_file(paths.diagnostics, layer="nodata")
        paths.diagnostics.with_name("diagnostics.json").unlink()
    # A run made before the coverage-policy update has no validation manifest.
    (output / "dem_coverage_inputs.json").unlink()
    before = {
        _tile_paths(output, p).terrain: _tile_paths(output, p)
        .terrain.stat()
        .st_mtime_ns
        for p in landuse_inputs
    }
    height_time = (output / "gebouwhoogten.gpkg").stat().st_mtime_ns
    boundary = tmp_path / "boundary.gpkg"
    gpd.GeoDataFrame(geometry=[box(32, 0, 64, 64)], crs=28992).to_file(
        boundary, layer="landgebied"
    )

    def no_recalculation(*args, **kwargs):
        raise AssertionError("Existing tiles and heights must be reused")

    monkeypatch.setattr(production, "calculate_building_elevations", no_recalculation)
    monkeypatch.setattr(interpolate, "interpolate_masked", no_recalculation)
    result = bouw_dem_tiles(
        output,
        ahn_vrt_path=ahn,
        landuse_tiles=landuse_inputs,
        config=config,
        landgebied_path=boundary,
    )
    assert result.is_file()
    assert (output / "dem_float.tif").is_file()
    assert (output / "gebouwhoogten.gpkg").stat().st_mtime_ns == height_time
    assert all(p.stat().st_mtime_ns == modified for p, modified in before.items())
    counts = json.loads((output / "dem_coverage.json").read_text())
    assert counts["outside_landgebied"] > 0
    assert counts["inside_landgebied_nonwater"] == 0
    assert "categorie" in wgpd.read_file(output / "nodata.gpkg").columns
    for tile in landuse_inputs:
        assert (
            "categorie" in wgpd.read_file(_tile_paths(output, tile).diagnostics).columns
        )
    # The validation boundary is pinned independently from reusable tile inputs.
    with pytest.raises(ValueError, match="coverage inputs changed"):
        bouw_dem_tiles(
            output, ahn_vrt_path=ahn, landuse_tiles=landuse_inputs, config=config
        )


@pytest.mark.parametrize("distance", [1.0, 2.0, 2.5])
def test_interpolation_respects_radial_limit_without_chaining(distance):
    data = np.full((11, 11), -9999, dtype="float32")
    data[5, 5] = 10
    result = interpolate.interpolate_masked(
        data,
        target_mask=data == -9999,
        donor_mask=data != -9999,
        max_distance_m=distance,
        pixel_width=1,
        pixel_height=1,
    )
    yy, xx = np.indices(data.shape)
    outside = np.hypot(yy - 5, xx - 5) > distance
    assert not result.filled_mask[outside].any()
    assert (result.values[outside] == -9999).all()


def test_landuse_writes_new_tile_folder_companions(tmp_path, landuse_inputs):
    from waterlagen.functioneel_landgebruik.gebouwen import validate_buildings
    from waterlagen.functioneel_landgebruik.paths import source_path

    target = (
        tmp_path
        / "new_tiles"
        / "000000_000000_000032_000032"
        / "functioneel_landgebruik.tif"
    )
    landuse.bouw_functioneel_landgebruik(
        target,
        bounds=(0, 0, 32, 32),
        resolution_m=1,
        gap_fill_distance_m=0,
        download_missing=False,
        building_index_path=tmp_path / "gebouw_index.sqlite",
        output_config=RasterOutputConfig(block_size=16, overview_factors=(2,)),
    )
    validate_buildings(target, 5)
    assert source_path(target) == target.with_name(
        "functioneel_landgebruik_bronnen.tif"
    )
    assert building_paths(target) == (
        target.with_name("gebouw_ids.tif"),
        target.with_name("gebouwen.gpkg"),
    )
    for new, old in zip(
        [target, source_path(target), building_paths(target)[0]],
        [
            landuse_inputs[0],
            source_path(landuse_inputs[0]),
            building_paths(landuse_inputs[0])[0],
        ],
        strict=True,
    ):
        np.testing.assert_array_equal(read(new), read(old))


def test_missing_float_export_repairs_without_rebuilding_integer_dem(
    tmp_path, landuse_inputs, monkeypatch
):
    from waterlagen.dem import productie
    from waterlagen.dem.exports import validate_float_dem

    ahn = write_ahn(
        tmp_path / "float_ahn.tif",
        np.ones((64, 64), dtype="int16"),
        scale=0.01,
        offset=-3,
    )
    result = bouw_dem_tiles(
        tmp_path / "float_repair", ahn_vrt_path=ahn, landuse_tiles=landuse_inputs
    )
    float_path = result.with_name("dem_float.tif")
    before = result.read_bytes(), result.stat().st_mtime_ns
    float_path.unlink()
    create = productie.create_float_dem

    def fail_export(*args):
        raise RuntimeError("simulated export failure")

    monkeypatch.setattr(productie, "create_float_dem", fail_export)
    with pytest.raises(RuntimeError, match="simulated"):
        bouw_dem_tiles(result.parent, ahn_vrt_path=ahn, landuse_tiles=landuse_inputs)
    assert not result.with_name("dem_complete.json").exists()
    assert result.with_name("dem_base_complete.json").exists()

    def must_not_rebuild(*args, **kwargs):
        pytest.fail("Valid integer DEM and tiles must be reused")

    monkeypatch.setattr(productie, "create_float_dem", create)
    monkeypatch.setattr(productie, "create_cog_file", must_not_rebuild)
    monkeypatch.setattr(productie, "calculate_building_elevations", must_not_rebuild)
    monkeypatch.setattr(interpolate, "interpolate_masked", must_not_rebuild)
    bouw_dem_tiles(result.parent, ahn_vrt_path=ahn, landuse_tiles=landuse_inputs)
    assert (result.read_bytes(), result.stat().st_mtime_ns) == before
    assert result.with_name("dem_complete.json").exists()
    validate_float_dem(result, float_path)


def test_tile_failure_finishes_other_dem_tiles_without_publication(
    tmp_path, landuse_inputs, monkeypatch
):
    from waterlagen.dem import productie

    ahn = write_ahn(tmp_path / "failure_ahn.tif", np.ones((64, 64), dtype="float32"))
    target = tmp_path / "failed_dem"
    original = productie._build_tile_worker
    attempted = []

    def build(arguments):
        attempted.append(arguments[0])
        if arguments[0] == landuse_inputs[0]:
            raise RuntimeError("synthetic failed tile")
        return original(arguments)

    monkeypatch.setattr(productie, "_build_tile_worker", build)
    with pytest.raises(RuntimeError, match="synthetic failed tile"):
        bouw_dem_tiles(
            target, ahn_vrt_path=ahn, landuse_tiles=landuse_inputs, workers=1
        )
    assert attempted == landuse_inputs
    assert not (target / "dem.tif").exists()
    assert not (target / "dem_complete.json").exists()
    assert _tile_paths(target, landuse_inputs[-1]).terrain.is_file()
