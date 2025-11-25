# %%
import logging
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
import rasterio
import requests
from osgeo import gdal
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from shapely.geometry import Polygon

from waterrasters import settings
from waterrasters.api_config import (
    AHN_CELL_SIZE_TYPE,
    AHN_MODEL_TYPE,
    AHN_SEVICE_TYPE,
    AHN_VERSION_TYPE,
    AHNService,
)

logger = logging.getLogger(__name__)
gdal.UseExceptions()


def get_tiles_gdf(
    ahn_service: AHNService,
    poly_mask: Polygon | None = None,
    select_indices: list[str] | None = None,
    model_type: AHN_MODEL_TYPE = "dtm",
    cell_size: AHN_CELL_SIZE_TYPE = "05",
    ahn_version: AHN_VERSION_TYPE = 4,
):
    # get AHN tiles in a GeoDataFrame
    gdf = ahn_service.get_tiles(
        ahn_version=ahn_version, model_type=model_type, cell_size=cell_size
    )

    # clip gdf
    if poly_mask is not None:
        gdf = gdf[gdf.intersects(poly_mask)]

    # select indices
    if select_indices is not None:
        gdf = gdf.loc[select_indices]

    return gdf


def create_vrt_file(download_dir: Path):
    # List of your GeoTIFF files
    download_dir = Path(download_dir)
    if download_dir.is_dir():
        tif_files = [
            i.absolute().resolve().as_posix() for i in download_dir.glob("*.tif")
        ]
        if len(tif_files) > 0:
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
        else:
            logging.warning(f"No vrt-file created as no files exist in {download_dir}")


def array_float_m_to_cm_int(
    data: npt.NDArray[np.int32], nodata: int
) -> tuple[npt.NDArray[np.int16], int]:
    """Create int16 numpy array from float32 numpy array

    Parameters
    ----------
    data : np.ndarray[np.int32]
        array with float32 data
    nodata : int
        nodata value in data

    Returns
    -------
    np.ndarray[np.int16], int
        int16 array in cm
    """
    # define out nodata as min lower bounds of int 16
    out_no_data = np.iinfo(np.int16).min

    # define nodata mask
    mask = data == nodata

    # scale data to cm
    scaled = np.empty_like(data, dtype=np.float32)
    scaled[mask] = 0
    scaled[~mask] = data[~mask] * 100

    # convert to int 16 and set nodata
    out = scaled.astype(np.int16)
    out[mask] = out_no_data

    return out, out_no_data


def create_download_dir(
    root_dir: Path,
    model_type: AHN_MODEL_TYPE = "dtm",
    cell_size: AHN_CELL_SIZE_TYPE = "05",
    ahn_version: AHN_SEVICE_TYPE = 4,
) -> Path:
    """Create a logic/unique download_dir as sub-directory of root_dir

    Parameters
    ----------
    root_dir : Path
        Root directory to create sub-directory for
    model_type : Literal[&quot;dtm&quot;, &quot;dsm&quot;], optional
        ahn model-type, by default "dtm"
    cell_size : Literal[&quot;05&quot;, &quot;5&quot;], optional
        ahn cell_size, by default "05"
    ahn_version : Literal[1, 2, 3, 4, 5, 6], optional
        ahn version, by default 4

    Returns
    -------
    Path
        ahn_directory
    """
    root_dir = Path(root_dir)
    download_dir = root_dir / f"AHN{ahn_version}_{model_type.upper()}_{cell_size}m"
    download_dir.mkdir(exist_ok=True, parents=True)
    return download_dir


def get_ahn_rasters(
    download_dir: Path,
    poly_mask: Polygon | None = None,
    select_indices: list[str] | None = None,
    model_type: AHN_MODEL_TYPE = "dtm",
    cell_size: AHN_CELL_SIZE_TYPE = "05",
    ahn_version: AHN_VERSION_TYPE = 4,
    service: Literal["ahn_pdok", "ahn_datastroom"] = "ahn_pdok",
    missing_only: bool = True,
    create_vrt: bool = True,
    save_tiles_index: bool = False,
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
    service : Literal["ahn_pdok", "ahn_datastroom"], optional
        Switch for using pdok.nl or ahn.nl for downloading ahn_data
    missing_only : bool, optional
        Only download rasters not yet existing in download_dir, by default True
    create_vrt : bool, optional
        Create a vrt-file so all tiles can be opened as one, by default True
    save_tiles_index : bool, optional
        Save the tile index as a GeoPackage in the download-dir, by default False

    Returns
    -------
    Path
        Path to download dir, being a sub-directory of ahn_root_dir
    """

    # int service
    ahn_service = AHNService(service=service)
    ahn_service._validate_inputs(cell_size=cell_size, ahn_version=ahn_version)
    # get AHN tiles as gdf
    tiles_gdf = get_tiles_gdf(
        poly_mask=poly_mask,
        select_indices=select_indices,
        ahn_service=ahn_service,
        model_type=model_type,
        cell_size=cell_size,
        ahn_version=ahn_version,
    )

    # make download dir if not existing
    download_dir = Path(download_dir)
    download_dir.mkdir(exist_ok=True, parents=True)

    # save index tiles
    if save_tiles_index:
        tiles_gdf.to_file(download_dir / "ahn_index.gpkg")

    # iteratively download AHN-tiles
    for row in tiles_gdf.itertuples():
        tile_index = row.Index
        file_path = download_dir / f"{tile_index}.tif"

        if (not missing_only) or (not file_path.exists()):
            logger.info(f"downloading {tile_index}")

            # dump existing file
            file_path.unlink(missing_ok=True)

            # get file
            url = getattr(row, ahn_service.download_url_field())
            response = requests.get(url)
            try:
                response.raise_for_status()
            except Exception as e:
                logger.error(e)
                continue

            # read tif in memory
            logger.info(f"writing {file_path}")
            with MemoryFile(response.content) as memfile:
                with memfile.open() as src:
                    # Read the data
                    data = src.read(1)  # Read first band; use read() for all bands
                    profile = src.profile.copy()

                # make it integer if user specified
                if settings.m_to_cm:
                    data, nodata = array_float_m_to_cm_int(data, nodata=src.nodata)
                    # update scales
                    scales = (0.01,)
                    profile.update(
                        dtype=np.int16,
                        nodata=nodata,
                    )
                else:
                    scales = (1.0,)

                # compression
                profile.update(
                    compress="deflate",
                    predictor=2,
                    tiled=True,
                )

                # write it to disc
                with rasterio.open(file_path, "w", **profile) as dst:
                    raster_cell_size = abs(dst.res[0])
                    dst.scales = scales
                    dst.write(data, 1)
                    # create overviews
                    factors = [
                        int(size / raster_cell_size)
                        for size in [5, 25]
                        if size > raster_cell_size
                    ]
                    dst.build_overviews(factors, Resampling.average)
                    dst.update_tags(ns="rio_overview", resampling="average")
    if create_vrt:
        create_vrt_file(download_dir)

    return download_dir
