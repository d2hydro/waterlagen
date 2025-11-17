# %%
import logging
from pathlib import Path
from typing import Literal

import geopandas as gpd
import numpy as np
import rasterio
import requests
from osgeo import gdal
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from shapely.geometry import Polygon

ROOT_URL = "https://service.pdok.nl/rws/ahn/atom/downloads"

logger = logging.getLogger(__name__)
gdal.UseExceptions()


def get_tiles_gdf(
    poly_mask: Polygon | None = None,
    select_indices: list[str] | None = None,
    ahn_type: str = "dtm_05m",
):
    # get url
    response = requests.get(f"{ROOT_URL}/{ahn_type}/kaartbladindex.json")
    response.raise_for_status()

    # convert to gdf
    gdf = gpd.GeoDataFrame.from_features(response.json(), crs=28992)

    # clip gdf
    if poly_mask is not None:
        gdf = gdf[gdf.intersects(poly_mask)]

    # select indices
    if select_indices is not None:
        gdf = gdf[gdf["kaartbladNr"].isin(select_indices)]

    return gdf


def create_vrt_file(download_dir: Path):
    # List of your GeoTIFF files
    download_dir = Path(download_dir)
    if download_dir.is_dir():
        tif_files = [
            i.absolute().resolve().as_posix() for i in download_dir.glob("*.tif")
        ]

        # Output VRT filename
        vrt_filename = download_dir / f"{download_dir.name}.vrt"

        # Build VRT
        vrt_options = gdal.BuildVRTOptions(
            resolution="average",
            separate=False,
            addAlpha=False,
            bandList=[1],
        )

        ds = gdal.BuildVRT(
            destName=vrt_filename.as_posix(),
            srcDSOrSrcDSTab=tif_files,
            options=vrt_options,
        )
        ds.FlushCache()


def get_ahn_rasters(
    download_dir: Path,
    poly_mask: Polygon | None = None,
    select_indices: list[str] | None = None,
    ahn_type: Literal["dtm_05m", "dsm_05m"] = "dtm_05m",
    missings_only: bool = True,
    create_vrt: bool = True,
    save_tiles_index: bool = False,
    as_int_16: bool = False,
):
    """Downloads AHN rasters

    Downloads ahn DTM or DSM rasters on 0.5m or 5m resolution

    Parameters
    ----------
    download_dir : Path
        Directory to store ahn-files.
    poly_mask : Polygon | None, optional
        Mask to select ahn-tiles, by default None
    select_indices : list[str] | None, optional
        Indices to select, by default None
    ahn_type : Literal["dtm_05m", "dsm_05m"], optional
        Download dtm, dsm, 0.5m or 5m, by default "dtm_05m"
    missings_only : bool, optional
        Only download rasters not yet existing in download_dir, by default True
    create_vrt : bool, optional
        Create a vrt-file so all tiles can be opened as one, by default True
    save_tiles_index : bool, optional
        Save the tile index as a GeoPackage in the download-dir, by default False
    as_int_16 : bool, optional
        Deflate as int 16 and values in cm + NAP, by default False
    """
    # get AHN tiles as gdf
    tiles_gdf = get_tiles_gdf(
        poly_mask=poly_mask, select_indices=select_indices, ahn_type=ahn_type
    )

    # make download dir
    download_dir = Path(download_dir)
    download_dir = download_dir / ahn_type
    download_dir.mkdir(exist_ok=True, parents=True)

    # save index tiles
    if save_tiles_index:
        tiles_gdf.to_file(download_dir / f"{ahn_type}.gpkg")

    # iteratively download AHN-tiles
    for row in tiles_gdf.itertuples():
        file_path = download_dir / f"{row.kaartbladNr}.tif"

        if missings_only and (not file_path.exists()):
            logger.info(f"downloading {row.kaartbladNr}")

            # get file
            try:
                response = requests.get(row.url)
                response.raise_for_status()
            except:
                continue

            # read tif in memory
            with MemoryFile(response.content) as memfile:
                with memfile.open() as src:
                    # Read the data
                    data = src.read(1)  # Read first band; use read() for all bands
                    profile = src.profile.copy()

                    # make it integer if user specified
                    if as_int_16:
                        data = np.where(
                            data != src.nodata, (data * 100), -32768
                        ).astype(np.int16)
                        profile.update(
                            dtype=np.int16,
                            compress="deflate",
                            predictor=2,
                            tiled=True,
                            driver="GTiff",
                            nodata=-32768,
                        )
                        scales = (0.01,)
                    else:
                        profile.update(
                            compress="deflate",
                            predictor=2,
                            tiled=True,
                            driver="GTiff",
                        )
                        scales = (1.0,)

                    # write it to disc
                    with rasterio.open(file_path, "w", **profile) as dst:
                        cell_size = abs(dst.res[0])
                        dst.scales = scales
                        dst.write(data, 1)
                        # create overviews
                        factors = [
                            int(size / cell_size)
                            for size in [5, 25]
                            if size > cell_size
                        ]
                        dst.build_overviews(factors, Resampling.average)
                        dst.update_tags(ns="rio_overview", resampling="average")
    if create_vrt:
        create_vrt_file(download_dir)
