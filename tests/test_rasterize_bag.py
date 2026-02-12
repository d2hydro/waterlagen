import numpy as np
import geopandas as gpd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from waterlagen.bag.rasterize import rasterize_bag


def _write_raster(path, data, *, nodata=-9999, scale=1.0):
    height, width = data.shape
    transform = from_origin(0, float(height), 1.0, 1.0)
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": data.dtype,
        "crs": "EPSG:28992",
        "transform": transform,
        "nodata": nodata,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.scales = (scale,)


def _make_gdf():
    geom = box(1, 1, 4, 4)
    return gpd.GeoDataFrame(geometry=[geom], crs="EPSG:28992")


def test_rasterize_bag_applies_scale_offset(tmp_path):
    dem = tmp_path / "dem_scale_001.tif"
    out = tmp_path / "out_scale_001.tif"
    data = np.full((5, 5), 100, dtype=np.int16)
    _write_raster(dem, data, scale=0.01)

    rasterize_bag(dem_raster=dem, bag_gdf=_make_gdf(), bag_pand_tif=out, buffer_step_m=0.1)

    with rasterio.open(out) as src:
        arr = src.read(1)
    assert arr.max() == 105


def test_rasterize_bag_no_scale_offset(tmp_path):
    dem = tmp_path / "dem_scale_1.tif"
    out = tmp_path / "out_scale_1.tif"
    data = np.full((5, 5), 100, dtype=np.int16)
    _write_raster(dem, data, scale=1.0)

    rasterize_bag(dem_raster=dem, bag_gdf=_make_gdf(), bag_pand_tif=out, buffer_step_m=0.1)

    with rasterio.open(out) as src:
        arr = src.read(1)
    assert arr.max() == 100
