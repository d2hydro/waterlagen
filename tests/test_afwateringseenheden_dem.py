from pathlib import Path

import numpy as np
import pytest
import rasterio
from osgeo import gdal
from pyproj import Transformer
from pyproj.exceptions import ProjError
from rasterio.transform import from_origin

from waterlagen.afwateringseenheden import dem
from waterlagen.afwateringseenheden._coverage import (
    _coverage_mask,
    _file_version,
    _vrt_sources,
)
from waterlagen.afwateringseenheden.raster import _resample_dem
from waterlagen.raster.grid import RasterGrid


def _write_raster(
    path: Path,
    values: np.ndarray,
    *,
    crs: str,
    left: float,
    top: float,
    scale: float,
    nodata: float | None = -9999,
) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        count=1,
        dtype=values.dtype,
        width=values.shape[1],
        height=values.shape[0],
        crs=crs,
        transform=from_origin(left, top, 1, 1),
        nodata=nodata,
    ) as output:
        output.write(values, 1)
        output.scales = (scale,)


def test_combined_dem_converts_heights_and_preserves_ahn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ahn_path = tmp_path / "ahn.tif"
    ahn_values = np.full((4, 4), 1000, dtype="int16")
    ahn_values[:, 2:] = -9999
    _write_raster(
        ahn_path, ahn_values, crs="EPSG:28992", left=188000, top=417004, scale=0.01
    )
    ahn_vrt = tmp_path / "ahn.vrt"
    with gdal.BuildVRT(str(ahn_vrt), [str(ahn_path)]):
        pass
    dgm_dir = tmp_path / "original"
    dgm_dir.mkdir()
    original = dgm_dir / "dgm1_test.tif"
    dgm_values = np.full((4, 8), 18.0, dtype="float32")
    _write_raster(
        original, dgm_values, crs="EPSG:25832", left=288000, top=5736504, scale=1
    )
    versions = {path: _file_version(path) for path in (ahn_path, ahn_vrt, original)}

    # Bekende synthetische XYZ-omzetting; geen netwerk of officiële grids nodig.
    transformer = Transformer.from_pipeline(
        "+proj=pipeline +step +proj=affine +xoff=-100000 +yoff=-5319500 +zoff=-0.25"
    )
    monkeypatch.setattr(dem, "_rdnap_transformer", lambda path: transformer)
    converted_dir = tmp_path / "converted"
    output = dem.prepare_ahn_dgm1_dem(
        ahn_vrt,
        dgm_dir,
        converted_dir=converted_dir,
        grid_dir=tmp_path / "grids",
        output_path=tmp_path / "combined.vrt",
    )
    converted = converted_dir / original.name
    with rasterio.open(converted) as check:
        assert check.crs.to_epsg() == 28992
        assert check.scales == (0.01,)
        assert check.tags()["vertical_datum"] == "NAP"
        np.testing.assert_array_equal(check.read(1), 1775)
    with rasterio.open(output) as check:
        expected = np.full((4, 8), 1775, dtype="int16")
        expected[:, :2] = 1000
        np.testing.assert_array_equal(check.read(1), expected)
        # Bestaande coverage en DEM-voorbereiding ondersteunen het vlakke mozaïek.
        grid = RasterGrid.from_bounds(
            (188000, 417000, 188010, 417004), resolution=1, crs="EPSG:28992"
        )
        coverage = _coverage_mask(check, grid)
        assert coverage[:, :8].all()
        assert not coverage[:, 8:].any()
        sampled = _resample_dem(check, grid, coverage)
        np.testing.assert_array_equal(sampled[:, :8], expected)
        assert np.isnan(sampled[:, 8:]).all()
    assert len(_vrt_sources(output, _file_version(output))) == 2

    version = _file_version(converted)
    dem.prepare_ahn_dgm1_dem(
        ahn_vrt,
        dgm_dir,
        converted_dir=converted_dir,
        grid_dir=tmp_path / "grids",
        output_path=tmp_path / "next_run.vrt",
    )
    assert _file_version(converted) == version
    for path, original_version in versions.items():
        assert _file_version(path) == original_version
    with pytest.raises(FileExistsError):
        dem.prepare_ahn_dgm1_dem(
            ahn_vrt,
            dgm_dir,
            converted_dir=converted_dir,
            grid_dir=tmp_path / "grids",
            output_path=output,
        )


@pytest.mark.parametrize(
    ("dtype", "nodata"),
    [("int16", -9999), ("float32", np.nan), ("float32", None)],
)
def test_converted_tile_reuses_matching_nodata(
    tmp_path: Path, dtype: str, nodata: float | None
) -> None:
    ahn_path = tmp_path / "ahn.tif"
    values = np.ones((2, 2), dtype=dtype)
    _write_raster(
        ahn_path,
        values,
        crs="EPSG:28992",
        left=188000,
        top=417004,
        scale=1,
        nodata=nodata,
    )
    grid = RasterGrid.from_bounds(
        (188000, 417002, 188002, 417004), resolution=1, crs="EPSG:28992"
    )
    converted = tmp_path / "converted.tif"
    conversion = {"vertical_datum": "NAP"}
    with rasterio.open(ahn_path) as ahn:
        dem._write_converted_tile(converted, values, grid, ahn, conversion)
        assert dem._reuse_converted_tile(converted, ahn, conversion)


def test_conversion_failure_does_not_publish_a_tile(tmp_path: Path) -> None:
    ahn_path = tmp_path / "ahn.tif"
    _write_raster(
        ahn_path,
        np.ones((2, 2), dtype="int16"),
        crs="EPSG:28992",
        left=188000,
        top=417004,
        scale=0.01,
    )
    original = tmp_path / "dgm1.tif"
    _write_raster(
        original,
        np.ones((2, 2), dtype="float32"),
        crs="EPSG:25832",
        left=288000,
        top=5736504,
        scale=1,
    )
    # Een grid buiten het geldige geografische domein moet hard falen.
    transformer = Transformer.from_pipeline("+proj=merc")
    output = tmp_path / "converted.tif"
    with (
        rasterio.open(ahn_path) as ahn,
        pytest.raises(ProjError, match="Invalid|latitude"),
    ):
        dem._convert_dgm1(original, output, ahn, transformer)
    assert not output.exists()
