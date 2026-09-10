import os
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import rasterio
from osgeo import gdal
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

from waterlagen.afwateringseenheden._coverage import _coverage_mask, _source_extent
from waterlagen.raster.grid import RasterGrid

CRS = "EPSG:28992"


def _source(path: Path, *, x: float = 0) -> Path:
    data = np.ones((8, 8), dtype="int16")
    data[:, :2] = -999
    data[3:5, 4:6] = -999
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        count=1,
        width=8,
        height=8,
        dtype="int16",
        nodata=-999,
        crs=CRS,
        transform=from_origin(x, 8, 1, 1),
    ) as destination:
        destination.write(data, 1)
    return path


def _vrt(path: Path, sources: list[Path]) -> Path:
    gdal.BuildVRT(str(path), list(map(str, sources))).FlushCache()
    return path


def test_full_extent_includes_nodata_collar_and_internal_hole(tmp_path) -> None:
    vrt = _vrt(tmp_path / "test.vrt", [_source(tmp_path / "source.tif")])
    grid = RasterGrid.from_bounds((0, 0, 8, 8), resolution=1, crs=CRS)
    with rasterio.open(vrt) as source:
        coverage = _coverage_mask(source, grid)
    assert coverage.all()


def test_overlap_and_missing_tiles_are_unioned_on_target_grid(tmp_path) -> None:
    paths = [_source(tmp_path / f"{i}.tif", x=x) for i, x in enumerate([0, 6, 20])]
    vrt = _vrt(tmp_path / "test.vrt", paths)
    grid = RasterGrid.from_bounds((-2, -2, 30, 10), resolution=1, crs=CRS)
    with rasterio.open(vrt) as source:
        coverage = _coverage_mask(source, grid)
    expected = np.zeros((12, 32), dtype=bool)
    expected[2:10, 2:16] = True
    expected[2:10, 22:30] = True
    assert np.array_equal(coverage, expected)


def test_cached_extents_are_invalidated_when_source_georeference_changes(
    tmp_path,
) -> None:
    path = _source(tmp_path / "source.tif")
    vrt = _vrt(tmp_path / "test.vrt", [path])
    grid = RasterGrid.from_bounds((0, 0, 8, 8), resolution=1, crs=CRS)
    with rasterio.open(vrt) as source:
        before = _coverage_mask(source, grid)
        misses = _source_extent.cache_info().misses
        assert np.array_equal(_coverage_mask(source, grid), before)
        assert _source_extent.cache_info().misses == misses
    previous = path.stat()
    with rasterio.open(path, "r+") as source:
        source.transform = from_origin(3, 8, 1, 1)
    os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns + 1_000_000_000))
    with rasterio.open(vrt) as source:
        after = _coverage_mask(source, grid)
    assert before[:, 2].all()
    assert not after[:, :3].any()
    assert after[:, 3:].all()
    assert _source_extent.cache_info().misses == misses + 1


def test_full_tiff_extent_ignores_vrt_crop_mapping_and_nodata_override(
    tmp_path,
) -> None:
    vrt = _vrt(tmp_path / "test.vrt", [_source(tmp_path / "source.tif")])
    tree = ET.parse(vrt)
    item = tree.find(".//ComplexSource")
    item.find("SrcRect").set("xOff", "2")
    item.find("SrcRect").set("xSize", "6")
    item.find("DstRect").set("xSize", "6")
    item.find("NODATA").text = "-123"
    tree.write(vrt)
    grid = RasterGrid.from_bounds((0, 0, 8, 8), resolution=1, crs=CRS)
    with rasterio.open(vrt) as source:
        coverage = _coverage_mask(source, grid)
    assert coverage.all()


def test_coverage_can_be_reprojected_to_a_shifted_target_grid(tmp_path) -> None:
    path = _source(tmp_path / "source.tif")
    with rasterio.open(path, "r+") as source:
        source.transform = from_origin(168000, 372000, 1, 1)
    bounds = transform_bounds(CRS, "EPSG:3857", 168000, 371992, 168008, 372000)
    grid = RasterGrid.from_bounds(bounds, resolution=1, crs="EPSG:3857")
    with rasterio.open(path) as source:
        coverage = _coverage_mask(source, grid)
    assert coverage.shape == (grid.height, grid.width)
    assert coverage.any()
    assert coverage.all()


def test_coverage_reads_metadata_only_even_for_all_nodata(
    tmp_path, monkeypatch
) -> None:
    from waterlagen.afwateringseenheden import _coverage

    path = _source(tmp_path / "empty.tif")
    with rasterio.open(path, "r+") as dataset:
        dataset.write(np.full((8, 8), -999, dtype="int16"), 1)
        dataset.write_mask(np.zeros((8, 8), dtype="uint8"))
    vrt = _vrt(tmp_path / "test.vrt", [path])
    grid = RasterGrid.from_bounds((-2, -2, 10, 10), resolution=2, crs=CRS)
    original_open = rasterio.open

    class MetadataOnly:
        def __enter__(self):
            self.dataset = original_open(path)
            self.driver = self.dataset.driver
            self.crs = self.dataset.crs
            self.bounds = self.dataset.bounds
            return self

        def __exit__(self, *args):
            self.dataset.close()

    with rasterio.open(vrt) as source:
        monkeypatch.setattr(_coverage.rasterio, "open", lambda *a, **kw: MetadataOnly())
        coverage = _coverage_mask(source, grid)
    expected = np.zeros((6, 6), dtype=bool)
    expected[1:5, 1:5] = True
    assert np.array_equal(coverage, expected)


def test_nodata_at_source_edges_is_filled_but_gaps_between_extents_are_not(
    tmp_path,
) -> None:
    from waterlagen.afwateringseenheden.raster import _resample_dem

    paths = [_source(tmp_path / f"{i}.tif", x=x) for i, x in enumerate([0, 12])]
    vrt = _vrt(tmp_path / "test.vrt", paths)
    grid = RasterGrid.from_bounds((-2, -2, 22, 10), resolution=2, crs=CRS)
    with rasterio.open(vrt) as source:
        coverage = _coverage_mask(source, grid)
        data = _resample_dem(source, grid, coverage)
    assert np.isfinite(data[coverage]).all()
    assert np.isnan(data[~coverage]).all()
