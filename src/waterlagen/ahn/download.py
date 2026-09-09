# %%
import io
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt
import rasterio
import requests
from osgeo import gdal
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from requests.models import Response
from shapely.geometry import Polygon

from waterlagen import datastore, settings
from waterlagen.ahn.api_config import AHNService
from waterlagen.logger import get_logger

logger = get_logger(__name__)
gdal.UseExceptions()


def _is_zipfile(response: Response) -> bool:
    """Return whether an AHN response is a ZIP archive."""
    content_type = response.headers.get("Content-Type", "").lower()
    response_url = str(getattr(response, "url", "")).lower()
    return "zip" in content_type or response_url.endswith(".zip")


@dataclass(frozen=True)
class _TileFailure:
    """Details of a tile that exhausted all configured download attempts."""

    tile_index: str
    url: str
    reason: str


def _validate_retries(retries: int) -> None:
    """Validate the maximum number of total download attempts per tile."""
    if not isinstance(retries, int) or isinstance(retries, bool):
        raise TypeError("retries must be an integer")
    if retries < 0:
        raise ValueError("retries must not be negative")


def _is_valid_ahn_tile(path: Path) -> bool:
    """Return whether path is a readable AHN TIFF with usable raster metadata."""
    path = Path(path)
    if not path.exists():
        return False

    try:
        with rasterio.open(path) as src:
            if src.width <= 0 or src.height <= 0 or src.count < 1:
                return False
            if src.crs is None or src.transform is None:
                return False
            if not src.profile.get("driver") or not src.dtypes[0]:
                return False
            src.read(1)
    except Exception as exc:
        logger.debug("Invalid AHN TIFF %s: %s", path, exc)
        return False
    return True


def _temporary_tile_path(file_path: Path) -> Path:
    """Create an unused temporary TIFF path beside its final tile path."""
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{file_path.name}.",
        suffix=".tif",
        dir=file_path.parent,
    )
    os.close(fd)
    temporary_path = Path(temporary_name)
    temporary_path.unlink(missing_ok=True)
    return temporary_path


def _tif_bytes_from_response(response: Response, *, tile_index: str) -> bytes:
    """Return a direct TIFF response or the first TIFF member from a ZIP response."""
    if not _is_zipfile(response):
        return response.content

    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        tif_names = [
            name for name in zip_file.namelist() if name.lower().endswith(".tif")
        ]
        if not tif_names:
            raise ValueError(f"No TIFF found in ZIP response for AHN tile {tile_index}")
        return zip_file.read(tif_names[0])


def _write_ahn_tile(temporary_path: Path, data_bytes: bytes) -> None:
    """Write an AHN response to a temporary TIFF and build its overviews."""
    with MemoryFile(data_bytes) as memfile:
        with memfile.open() as source:
            data = source.read(1)
            profile = source.profile.copy()
            source_nodata = source.nodata

    if settings.m_to_cm:
        data, nodata = array_float_m_to_cm_int(data, nodata=source_nodata)
        scales = (0.01,)
        profile.update(dtype=np.int16, nodata=nodata)
    else:
        scales = (1.0,)

    profile.update(compress="deflate", predictor=2, tiled=True)
    with rasterio.open(temporary_path, "w", **profile) as destination:
        raster_cell_size = abs(destination.res[0])
        destination.scales = scales
        destination.write(data, 1)
        factors = [
            int(size / raster_cell_size) for size in [5, 25] if size > raster_cell_size
        ]
        destination.build_overviews(factors, Resampling.average)
        destination.update_tags(ns="rio_overview", resampling="average")


def get_tiles_features(
    ahn_service: AHNService,
    poly_mask: Polygon | None = None,
    select_indices: list[str] | None = None,
    model: Literal["dtm", "dsm"] = "dtm",
    cell_size: Literal["05", "5"] = "05",
    ahn_version: Literal[3, 4, 5, 6] = 4,
):
    # get AHN tiles in a GeoDataFrame
    gdf = ahn_service.get_tiles(
        ahn_version=ahn_version, model=model, cell_size=cell_size
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
            vrt_file = download_dir / f"{download_dir.name}.vrt"

            # Build VRT
            vrt_options = gdal.BuildVRTOptions(
                resolution="average",
                separate=False,
                addAlpha=False,
                bandList=[1],
            )

            ds = gdal.BuildVRT(
                destName=vrt_file.as_posix(),
                srcDSOrSrcDSTab=tif_files,
                options=vrt_options,
            )
            ds.FlushCache()
        else:
            logger.warning(f"No vrt-file created as no files exist in {download_dir}")

    return vrt_file


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
    model: Literal["dtm", "dsm"] = "dtm",
    cell_size: Literal["05", "5"] = "05",
    ahn_version: Literal[3, 4, 5, 6] = 4,
) -> Path:
    """Create a logic/unique download_dir as sub-directory of root_dir

    Parameters
    ----------
    root_dir : Path
        Root directory to create sub-directory for
    model : Literal[&quot;dtm&quot;, &quot;dsm&quot;], optional
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
    download_dir = root_dir / f"AHN{ahn_version}_{model.upper()}_{cell_size}m"
    download_dir.mkdir(exist_ok=True, parents=True)
    return download_dir


def download_ahn(
    ahn_dir: Path = datastore.ahn_dir,
    poly_mask: Polygon | None = None,
    select_indices: list[str] | None = None,
    model: Literal["dtm", "dsm"] = "dtm",
    cell_size: Literal["05", "5"] = "05",
    ahn_version: Literal[3, 4, 5, 6] = 4,
    service: Literal["ahn_pdok", "ahn_nl"] = "ahn_pdok",
    missing_only: bool = True,
    create_vrt: bool = True,
    save_tiles_index: bool = False,
    *,
    retries: int = 10,
) -> Path:
    """Download AHN rasters with validated, atomic tile replacement.

    Downloads AHN DTM or DSM rasters on 0.5 m or 5 m resolution. Each
    response is written to a temporary TIFF beside its target, processed,
    closed, reopened, and validated before it atomically replaces the final
    tile. A valid existing tile is reused with ``missing_only=True``. An
    invalid existing tile is removed and downloaded again.

    Parameters
    ----------
    ahn_dir : Path, optional
        Directory to store ahn-files. Defaults to datastore.ahn_dir
    poly_mask : Polygon | None, optional
        Mask to select ahn-tiles, by default None
    select_indices : list[str] | None, optional
        Indices to select, by default None
    service : Literal["ahn_pdok", "ahn_nl"], optional
        Switch for using pdok.nl or ahn.nl for downloading ahn_data
    missing_only : bool, optional
        Only download rasters not yet existing in download_dir, by default True
    create_vrt : bool, optional
        Create a vrt-file so all tiles can be opened as one, by default True
    save_tiles_index : bool, optional
        Save the tile index as a GeoPackage in the download-dir, by default False
    retries : int, optional
        Maximum total download attempts for each tile, by default 10. Set to 0
        to make every requested tile fail without an HTTP request.

    Returns
    -------
    Path
        Path to download dir or vrt_file, being a sub-directory of ahn_root_dir
    """

    _validate_retries(retries)

    # init service
    ahn_service = AHNService(service=service)
    ahn_service._validate_inputs(cell_size=cell_size, ahn_version=ahn_version)
    # get AHN tiles as gdf
    tiles_gdf = get_tiles_features(
        poly_mask=poly_mask,
        select_indices=select_indices,
        ahn_service=ahn_service,
        model=model,
        cell_size=cell_size,
        ahn_version=ahn_version,
    )

    # make download dir if not existing
    download_dir = Path(ahn_dir).joinpath(f"{model}_{cell_size}")
    download_dir.mkdir(exist_ok=True, parents=True)

    # save index tiles
    if save_tiles_index:
        tiles_gdf.to_file(download_dir / f"{download_dir.name}.gpkg")

    valid_tiles = 0
    retried_tiles = 0
    failed_tiles: list[_TileFailure] = []

    # Iteratively download AHN tiles. Failures are collected so the caller gets
    # every failed tile instead of an incomplete dataset without an exception.
    with rasterio.Env():
        for row in tiles_gdf.itertuples():
            tile_index = row.Index
            file_path = download_dir / f"{tile_index}.tif"
            url = getattr(
                row,
                ahn_service.download_url_field(
                    model=model,
                    cell_size=cell_size,
                    ahn_version=ahn_version,
                ),
            )
            existing_tile_is_valid = False
            invalid_existing_tile = False

            if file_path.exists():
                existing_tile_is_valid = _is_valid_ahn_tile(file_path)
                if existing_tile_is_valid and missing_only:
                    logger.info(
                        "Reusing valid AHN tile %s from %s at %s",
                        tile_index,
                        url,
                        file_path,
                    )
                    valid_tiles += 1
                    continue
                if not existing_tile_is_valid:
                    invalid_existing_tile = True
                    logger.warning(
                        "Existing AHN tile %s at %s is invalid or incomplete; "
                        "removing it before download from %s",
                        tile_index,
                        file_path,
                        url,
                    )
                    try:
                        file_path.unlink()
                    except OSError as exc:
                        reason = f"could not remove invalid existing tile: {exc}"
                        logger.error(
                            "Failed AHN tile %s from %s to %s: %s",
                            tile_index,
                            url,
                            file_path,
                            reason,
                        )
                        failed_tiles.append(
                            _TileFailure(
                                tile_index=str(tile_index),
                                url=str(url),
                                reason=reason,
                            )
                        )
                        continue

            tile_was_retried = invalid_existing_tile
            successful = False
            last_error: Exception | None = None
            for attempt in range(1, retries + 1):
                temporary_path: Path | None = None
                logger.info(
                    "Downloading AHN tile %s, attempt %s/%s, from %s to %s",
                    tile_index,
                    attempt,
                    retries,
                    url,
                    file_path,
                )
                try:
                    temporary_path = _temporary_tile_path(file_path)
                    response = requests.get(url)
                    response.raise_for_status()
                    data_bytes = _tif_bytes_from_response(
                        response,
                        tile_index=str(tile_index),
                    )
                    _write_ahn_tile(temporary_path, data_bytes)
                    if not _is_valid_ahn_tile(temporary_path):
                        raise ValueError(
                            f"Temporary AHN TIFF validation failed: {temporary_path}"
                        )
                    logger.info(
                        "Validated temporary AHN tile %s at %s",
                        tile_index,
                        temporary_path,
                    )
                    temporary_path.replace(file_path)
                    logger.info(
                        "Successfully validated AHN tile %s at %s",
                        tile_index,
                        file_path,
                    )
                    valid_tiles += 1
                    if tile_was_retried or attempt > 1:
                        retried_tiles += 1
                    successful = True
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < retries:
                        logger.warning(
                            "AHN tile %s, attempt %s/%s from %s to %s failed; "
                            "retrying: %s",
                            tile_index,
                            attempt,
                            retries,
                            url,
                            file_path,
                            exc,
                        )
                    else:
                        logger.warning(
                            "AHN tile %s, final attempt %s/%s from %s to %s failed: %s",
                            tile_index,
                            attempt,
                            retries,
                            url,
                            file_path,
                            exc,
                        )
                finally:
                    if temporary_path is not None:
                        try:
                            temporary_path.unlink(missing_ok=True)
                        except OSError as cleanup_error:
                            logger.warning(
                                "Could not remove temporary AHN tile %s: %s",
                                temporary_path,
                                cleanup_error,
                            )

            if successful:
                continue

            if last_error is None:
                reason = f"no download attempts configured (retries={retries})"
            else:
                reason = str(last_error)
            logger.error(
                "Failed AHN tile %s from %s to %s after %s attempts: %s",
                tile_index,
                url,
                file_path,
                retries,
                reason,
            )
            failed_tiles.append(
                _TileFailure(
                    tile_index=str(tile_index),
                    url=str(url),
                    reason=reason,
                )
            )

    if failed_tiles:
        logger.error(
            "AHN download failed: %s valid, %s retried, %s failed",
            valid_tiles,
            retried_tiles,
            len(failed_tiles),
        )
        failures = "; ".join(
            f"{failure.tile_index} ({failure.url}): {failure.reason}"
            for failure in failed_tiles
        )
        raise RuntimeError(f"AHN download failed for tiles: {failures}")

    logger.info(
        "AHN download completed: %s valid, %s retried, 0 failed",
        valid_tiles,
        retried_tiles,
    )
    if create_vrt:
        vrt_file = create_vrt_file(download_dir)
        return vrt_file
    else:
        return download_dir


def get_ahn_rasters(*args, **kwargs) -> Path:
    """Compatibility alias for :func:`download_ahn`."""
    return download_ahn(*args, **kwargs)
