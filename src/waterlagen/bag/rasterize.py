from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.io import DatasetReader
from rasterio.mask import mask
from shapely.geometry import Polygon, mapping


def sample_polygon(
    polygon: Polygon, raster_src: DatasetReader, percentile: int = 75, band: int = 1
) -> int:
    """Sample raster over polygon

    Parameters
    ----------
    polygon : Polygon
        Input polygon
    raster_src : DatasetReader
        Opened rasterio DatasetReader
    percentile : int, optional
        Percentile-value to find, by default 75
    band : int, optional
        Raster-band, by default 1

    Returns
    -------
    int
        Raster sample value
    """
    nodata = raster_src.nodata

    data, _ = mask(
        raster_src, [polygon], crop=True, filled=True, nodata=nodata, indexes=band
    )

    if nodata is not None:
        data = data[data != nodata]

    if data.size:
        value = np.percentile(data, percentile).astype(data.dtype)
    else:
        value = None

    return value


def buffered_elevation_search(
    polygon: Polygon,
    raster_src: DatasetReader,
    buffer_step_m: float = 1,
    percentile: int = 75,
    band: int = 1,
    max_iters: int = 20,
):
    """Buffer iteratively and find elevation percentile of surrounding raster cells

    Parameters
    ----------
    polygon : Polygon
        Initial polygon
    raster_src : DatasetReader
        Opened rasterio DatasetReader
    buffer_step_m : float, optional
        Buffer increment to find values, by default 1
    percentile : int, optional
        Percentile-value to find, by default 75
    elevation_offset: float, optional
        Elevation offset above elevation found from
    band : int, optional
        Raster-band, by default 1
    max_iters : int, optional
        Max iters to buffer. If exceeded function will return None, by default 20

    Returns
    -------
    _type_
        _description_
    """
    for _ in range(max_iters):
        polygon = polygon.buffer(buffer_step_m)
        value = sample_polygon(
            polygon=polygon, raster_src=raster_src, percentile=percentile, band=band
        )
        if value is not None:
            return value


def rasterize_bag(
    dem_raster: Path,
    bag_gdf: gpd.GeoDataFrame,
    bag_pand_tif: Path,
    buffer_step_m: float,
    elevation_offset_m: float = 0.05,
):
    with rasterio.open(dem_raster) as raster_src:
        if raster_src.scales[0] == 0.01:
            elevation_offset = round((elevation_offset_m * 100))
        else:
            elevation_offset = elevation_offset_m
        bag_gdf["vloerpeil"] = [
            buffered_elevation_search(
                polygon=geom, raster_src=raster_src, buffer_step_m=buffer_step_m
            )
            for geom in bag_gdf.geometry
        ]

        shapes = (
            (mapping(geom), int(val))
            for geom, val in zip(
                bag_gdf.geometry,
                bag_gdf["vloerpeil"] + elevation_offset,
            )
        )

        profile = raster_src.profile
        profile["driver"] = "GTiff"
        with rasterio.open(bag_pand_tif, mode="w", **profile) as dst:
            data = rasterize(
                shapes=shapes,
                out_shape=raster_src.shape,
                transform=raster_src.transform,
                fill=raster_src.nodata,
                dtype=raster_src.profile["dtype"],
                all_touched=False,
            )
            dst.scales = raster_src.scales
            dst.write(data, 1)
