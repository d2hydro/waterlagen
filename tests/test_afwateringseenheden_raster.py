from pathlib import Path
from hashlib import sha256

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from osgeo import gdal
from rasterio.transform import from_origin
from shapely.geometry import LineString, box

from waterlagen.afwateringseenheden import prepare_watersysteem_rasters
from waterlagen.afwateringseenheden import raster as raster_module
from waterlagen.afwateringseenheden._coverage import _file_version
from waterlagen.settings import settings

CRS = settings.crs
NODATA = -32768


@pytest.mark.parametrize("boundary_crs", [CRS, "EPSG:3857"])
def test_landsgrens_fills_dutch_cells_only_and_invalidates_unmasked_cache(
    source_paths, tmp_path, monkeypatch, boundary_crs
) -> None:
    ahn_vrt_path, watersysteem_path = source_paths
    landsgrens_path = tmp_path / "bestuurlijke.gpkg"
    boundary = gpd.GeoDataFrame(geometry=[box(0, 0, 4, 8)], crs=CRS)
    boundary.to_crs(boundary_crs).to_file(landsgrens_path, layer="landgebied")
    kwargs = {
        "burn_depth_m": 0,
        "ahn_vrt_path": ahn_vrt_path,
        "watersysteem_path": watersysteem_path,
        "output_dir": tmp_path / "output",
    }
    # Existing unmasked output must not hide the newly requested boundary.
    result = prepare_watersysteem_rasters(box(0, 0, 8, 8), **kwargs)
    with rasterio.open(result.dem_path) as dem:
        assert not np.ma.getmaskarray(dem.read(1, masked=True)).any()
    kwargs["landsgrens_path"] = landsgrens_path
    prepare_watersysteem_rasters(box(0, 0, 8, 8), **kwargs)
    with rasterio.open(result.dem_path) as dem:
        data = dem.read(1, masked=True)
        assert not np.ma.getmaskarray(data[:, :2]).any()
        assert np.all(data[:, :2] == 1000)
        assert np.ma.getmaskarray(data[:, 2:]).all()
        assert dem.scales == (0.01,)
        assert dem.nodata == NODATA
    version = result.dem_path.stat().st_mtime_ns
    monkeypatch.setattr(
        raster_module,
        "_resample_dem",
        lambda *args: pytest.fail("unchanged boundary should reuse rasters"),
    )
    assert prepare_watersysteem_rasters(box(0, 0, 8, 8), **kwargs) == result
    assert result.dem_path.stat().st_mtime_ns == version


def test_prepare_regenerates_old_landsgrens_mask_at_a_touching_edge(
    source_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    ahn_vrt_path, watersysteem_path = source_paths
    boundary_path = tmp_path / "bestuurlijke.gpkg"
    gpd.GeoDataFrame(geometry=[box(-8, 0, 0, 8)], crs=CRS).to_file(
        boundary_path, layer="landgebied"
    )
    options = {
        "burn_depth_m": 0,
        "ahn_vrt_path": ahn_vrt_path,
        "watersysteem_path": watersysteem_path,
        "landsgrens_path": boundary_path,
        "output_dir": tmp_path / "output",
    }
    result = prepare_watersysteem_rasters(box(0, 0, 8, 8), **options)
    # Previous masking rasterized the touching edge as a false strip of coverage.
    previous_version = sha256(
        f"{boundary_path.resolve()}:{_file_version(boundary_path)}".encode()
    ).hexdigest()
    with rasterio.open(result.dem_path, "r+") as dem:
        data = dem.read(1)
        data[:, 0] = 1000
        dem.write(data, 1)
        dem.update_tags(waterlagen_dem_landsgrens=previous_version)

    assert prepare_watersysteem_rasters(box(0, 0, 8, 8), **options) == result

    with rasterio.open(result.dem_path) as dem:
        assert np.ma.getmaskarray(dem.read(1, masked=True)).all()
        assert dem.tags()["waterlagen_dem_landsgrens"] != previous_version


def _write_ahn_vrt(tmp_path: Path) -> Path:
    source_path = tmp_path / "dtm_05.tif"
    data = np.full((16, 16), 1000, dtype=np.int16)
    data[4:12, 4:12] = NODATA
    with rasterio.open(
        source_path,
        "w",
        driver="GTiff",
        width=16,
        height=16,
        count=1,
        dtype="int16",
        nodata=NODATA,
        crs=CRS,
        transform=from_origin(0, 8, 0.5, 0.5),
    ) as destination:
        destination.scales = (0.01,)
        destination.write(data, 1)

    vrt_path = tmp_path / "dtm_05.vrt"
    gdal.BuildVRT(str(vrt_path), [str(source_path)]).FlushCache()
    return vrt_path


def _write_watersysteem(path: Path) -> Path:
    primary = gpd.GeoDataFrame(
        {"naam": ["primair"]},
        geometry=[LineString([(1, 0), (1, 8)])],
        crs=CRS,
    )
    secondary = gpd.GeoDataFrame(
        {"naam": ["secundair"]},
        geometry=[LineString([(0, 1), (8, 1)])],
        crs=CRS,
    )
    segments = gpd.GeoDataFrame(
        {"segment_id": ["primair:0001", "primair:0002"]},
        geometry=[
            LineString([(1, 0), (1, 8)]),
            LineString([(3, 0), (3, 8)]),
        ],
        crs=CRS,
    )
    primary.to_file(path, layer="hydroobject_primair", driver="GPKG", index=False)
    secondary.to_file(path, layer="hydroobject_secundair", mode="a", index=False)
    segments.to_file(path, layer="hydroobject_segment", mode="a", index=False)
    return path


@pytest.fixture
def source_paths(tmp_path: Path) -> tuple[Path, Path]:
    return _write_ahn_vrt(tmp_path), _write_watersysteem(tmp_path / "watersysteem.gpkg")


def test_prepare_watersysteem_rasters_preserves_grid_scale_and_burn_priority(
    source_paths: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    ahn_vrt_path, watersysteem_path = source_paths

    result = prepare_watersysteem_rasters(
        box(0, 0, 8, 8),
        burn_depth_m=1.5,
        ahn_vrt_path=ahn_vrt_path,
        watersysteem_path=watersysteem_path,
        output_dir=tmp_path / "output",
    )

    with (
        rasterio.open(result.dem_path) as dem,
        rasterio.open(result.hydroobject_segment_path) as segments,
    ):
        assert dem.crs == segments.crs
        assert dem.transform == segments.transform
        assert dem.res == segments.res == (2.0, 2.0)
        assert dem.shape == segments.shape == (4, 4)
        assert dem.dtypes == ("int16",)
        assert dem.scales == (0.01,)
        assert not np.ma.getmaskarray(dem.read(1, masked=True)).any()

        elevations = dem.read(1)
        assert np.all(elevations[:, 0] == 700)
        assert np.all(elevations[-1, 1:] == 850)
        assert elevations[-1, 0] == 700

        segment_values = segments.read(1)
        assert np.all(segment_values[:, 0] == 1)
        assert np.all(segment_values[:, 1] == 2)
        assert np.all(segment_values[:, 2:] == 0)


def test_fill_dem_nodata_fills_internal_gaps() -> None:
    data = np.array(
        [
            [0.0, 1.0, 2.0],
            [1.0, np.nan, 3.0],
            [2.0, 3.0, 4.0],
        ]
    )

    result = raster_module._fill_dem_nodata(data)

    assert np.isfinite(result).all()


def test_fill_dem_nodata_searches_the_full_raster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = np.array(
        [
            [np.nan, np.nan, np.nan],
            [np.nan, 2.0, np.nan],
            [np.nan, np.nan, np.nan],
        ]
    )

    observed: dict[str, np.ndarray | float] = {}

    def fake_fillnodata(
        image: np.ndarray,
        *,
        mask: np.ndarray,
        max_search_distance: float,
        nodata: float,
    ) -> np.ndarray:
        observed["mask"] = mask
        observed["max_search_distance"] = max_search_distance
        return np.full(image.shape, 2.0)

    monkeypatch.setattr(raster_module, "fillnodata", fake_fillnodata)

    result = raster_module._fill_dem_nodata(data)

    assert np.all(result == 2.0)
    assert np.array_equal(observed["mask"], np.isfinite(data))
    assert observed["max_search_distance"] == pytest.approx(np.hypot(*data.shape))


@pytest.mark.parametrize("unfilled", [np.nan, np.inf, np.finfo(np.float32).min])
def test_fill_dem_nodata_recovers_only_remaining_gaps(
    monkeypatch: pytest.MonkeyPatch, unfilled: float
) -> None:
    data = np.array([[1.123456789, np.nan, np.nan, 4.123456789]])
    original = data.copy()
    monkeypatch.setattr(
        raster_module,
        "fillnodata",
        lambda *args, **kwargs: np.array([[1.0, 2.5, unfilled, 4.0]]),
    )

    result = raster_module._fill_dem_nodata(data)

    np.testing.assert_array_equal(result, [[data[0, 0], 2.5, data[0, 3], data[0, 3]]])
    np.testing.assert_array_equal(data, original)


def test_fill_dem_nodata_recovers_an_isolated_covered_edge_cell(caplog) -> None:
    data = np.full((3, 3), np.nan)
    data[2, 0] = 10.123456789
    original = data.copy()
    coverage = np.isfinite(data)
    coverage[0, 2] = True

    with caplog.at_level("INFO", logger=raster_module.__name__):
        result = raster_module._fill_dem_nodata(data, coverage)

    assert result[0, 2] == data[2, 0]
    assert result[2, 0] == data[2, 0]
    assert np.isnan(result[~coverage]).all()
    assert "Filling 1 remaining covered DEM cells" in caplog.text
    np.testing.assert_array_equal(data, original)


def test_nearest_dem_value_searches_beyond_the_first_window_with_donors() -> None:
    data = np.full((11, 11), np.nan)
    data[9, 9] = 10.0  # Found in radius 4, but farther away than the next donor.
    data[0, 5] = 20.0
    donors = np.isfinite(data)

    assert raster_module._nearest_dem_value(data, donors, 5, 5) == 20.0


def test_fill_dem_nodata_excludes_finite_outside_values_as_donors() -> None:
    data = np.full((3, 3), np.nan)
    data[2, 0] = 10.0
    data[0, 1] = 999.0
    coverage = np.zeros(data.shape, dtype=bool)
    coverage[2, 0] = True
    coverage[0, 2] = True

    result = raster_module._fill_dem_nodata(data, coverage)

    assert result[0, 2] == 10.0
    np.testing.assert_array_equal(result[~coverage], data[~coverage])


@pytest.mark.parametrize("outside_value", [np.nan, 999.0])
def test_fill_dem_nodata_rejects_coverage_without_donors(outside_value) -> None:
    data = np.array([[np.nan, outside_value]])
    coverage = np.array([[True, False]])

    with pytest.raises(ValueError, match="no finite elevation values"):
        raster_module._fill_dem_nodata(data, coverage)


def test_resample_dem_rejects_a_square_outside_the_ahn_vrt(
    source_paths: tuple[Path, Path],
) -> None:
    ahn_vrt_path, _ = source_paths
    grid = raster_module._grid_for_square(box(10, 10, 18, 18), resolution_m=2)

    with (
        rasterio.open(ahn_vrt_path) as source,
        pytest.raises(ValueError, match="does not intersect AHN VRT extent"),
    ):
        raster_module._resample_dem(source, grid)


def test_prepare_watersysteem_rasters_cleans_temporary_files_after_failure(
    source_paths: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ahn_vrt_path, watersysteem_path = source_paths
    output_dir = tmp_path / "output"

    def fail_write(*args, **kwargs) -> None:
        raise RuntimeError("segment raster write failed")

    monkeypatch.setattr(raster_module, "_write_segment_raster", fail_write)

    with pytest.raises(RuntimeError, match="segment raster write failed"):
        prepare_watersysteem_rasters(
            box(0, 0, 8, 8),
            burn_depth_m=1.5,
            ahn_vrt_path=ahn_vrt_path,
            watersysteem_path=watersysteem_path,
            output_dir=output_dir,
        )

    assert not list(output_dir.glob(".*.tif.*.tif"))
    assert not (output_dir / "dem_2m.tif").exists()
    assert not (output_dir / "hydroobject_segment.tif").exists()


def test_prepare_watersysteem_rasters_reuses_a_valid_pair(
    source_paths: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ahn_vrt_path, watersysteem_path = source_paths
    output_dir = tmp_path / "output"
    expected = prepare_watersysteem_rasters(
        box(0, 0, 8, 8),
        burn_depth_m=1.5,
        ahn_vrt_path=ahn_vrt_path,
        watersysteem_path=watersysteem_path,
        output_dir=output_dir,
    )
    monkeypatch.setattr(
        raster_module,
        "_resample_dem",
        lambda *args, **kwargs: pytest.fail("valid rasters should be reused"),
    )

    result = prepare_watersysteem_rasters(
        box(0, 0, 8, 8),
        burn_depth_m=1.5,
        ahn_vrt_path=ahn_vrt_path,
        watersysteem_path=watersysteem_path,
        output_dir=output_dir,
        overwrite=False,
    )

    assert result == expected


def test_fill_excludes_outside_targets_and_preserves_finite_values(monkeypatch) -> None:
    coverage = np.zeros((9, 9), dtype=bool)
    coverage[1:8, 1:6] = True
    data = np.full(coverage.shape, np.nan)
    data[coverage] = 10.123456789
    data[4, 3] = np.nan
    valid = np.isfinite(data)
    original_fill = raster_module.fillnodata

    def checked_fill(image, *, mask, max_search_distance, nodata):
        assert np.array_equal(mask == 0, coverage & ~valid)
        assert np.all(mask[~coverage])
        assert np.all(image[~coverage] == nodata)
        assert max_search_distance == pytest.approx(np.hypot(*data.shape))
        return original_fill(
            image, mask=mask, max_search_distance=max_search_distance, nodata=nodata
        )

    monkeypatch.setattr(raster_module, "fillnodata", checked_fill)
    result = raster_module._fill_dem_nodata(data, coverage)
    assert np.array_equal(result[valid], data[valid])
    assert np.isfinite(result[coverage]).all()
    assert np.isnan(result[~coverage]).all()
    assert result[4, 3] == pytest.approx(10.123456789)


def test_no_interpolation_for_exterior_nodata_only(monkeypatch) -> None:
    data = np.array([[1.0, np.nan]])
    monkeypatch.setattr(
        raster_module, "fillnodata", lambda *a, **kw: pytest.fail("No targets")
    )
    result = raster_module._fill_dem_nodata(data, np.array([[True, False]]))
    assert np.array_equal(result, data, equal_nan=True)


def test_prepare_preserves_exterior_nodata_through_burning_and_reuse(
    source_paths, tmp_path
) -> None:
    vrt, watersysteem = source_paths
    kwargs = {
        "burn_depth_m": 1.5,
        "ahn_vrt_path": vrt,
        "watersysteem_path": watersysteem,
        "output_dir": tmp_path / "covered",
    }
    result = prepare_watersysteem_rasters(box(-2, -2, 10, 10), **kwargs)
    with rasterio.open(result.dem_path) as source:
        values = source.read(1, masked=True)
        assert source.nodata == NODATA
        assert values[1:5, 1:5].count() == 16
        assert values.count() == 16
        assert (
            source.tags()["waterlagen_dem_coverage"] == raster_module.COVERAGE_VERSION
        )
    assert prepare_watersysteem_rasters(box(-2, -2, 10, 10), **kwargs) == result


def test_old_outputs_without_coverage_policy_are_regenerated(
    source_paths, tmp_path
) -> None:
    vrt, watersysteem = source_paths
    kwargs = {
        "burn_depth_m": 1.5,
        "ahn_vrt_path": vrt,
        "watersysteem_path": watersysteem,
        "output_dir": tmp_path / "old",
    }
    result = prepare_watersysteem_rasters(box(0, 0, 8, 8), **kwargs)
    with rasterio.open(result.dem_path, "r+") as source:
        source.update_tags(waterlagen_dem_coverage="source_extents_v1")
        source.write(np.full((4, 4), -123, dtype="int16"), 1)
    prepare_watersysteem_rasters(box(0, 0, 8, 8), **kwargs)
    with rasterio.open(result.dem_path) as source:
        assert (
            source.tags()["waterlagen_dem_coverage"] == raster_module.COVERAGE_VERSION
        )
        assert not np.any(source.read(1) == -123)
