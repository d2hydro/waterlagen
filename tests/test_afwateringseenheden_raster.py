from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from osgeo import gdal
from rasterio.transform import from_origin
from shapely.geometry import LineString, box

from waterlagen.afwateringseenheden import prepare_watersysteem_rasters
from waterlagen.afwateringseenheden import raster as raster_module
from waterlagen.settings import settings

CRS = settings.crs
NODATA = -32768


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
    ) -> np.ndarray:
        observed["mask"] = mask
        observed["max_search_distance"] = max_search_distance
        return np.full(image.shape, 2.0)

    monkeypatch.setattr(raster_module, "fillnodata", fake_fillnodata)

    result = raster_module._fill_dem_nodata(data)

    assert np.all(result == 2.0)
    assert np.array_equal(observed["mask"], np.isfinite(data))
    assert observed["max_search_distance"] == pytest.approx(np.hypot(*data.shape))


def test_fill_dem_nodata_raises_when_gaps_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = np.array([[1.0, np.nan]])
    monkeypatch.setattr(raster_module, "fillnodata", lambda *args, **kwargs: data)

    with pytest.raises(ValueError, match="1 non-finite cell"):
        raster_module._fill_dem_nodata(data)


def test_resample_dem_rejects_a_square_outside_the_ahn_vrt(
    source_paths: tuple[Path, Path],
) -> None:
    ahn_vrt_path, _ = source_paths
    grid = raster_module._grid_for_square(box(10, 10, 18, 18), resolution_m=2)

    with rasterio.open(ahn_vrt_path) as source:
        with pytest.raises(ValueError, match="does not intersect AHN VRT extent"):
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
