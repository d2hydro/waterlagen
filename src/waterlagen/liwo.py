"""Download het LIWO-klassenraster en polygoniseer uitsluitend klassen 1 en 6."""

import tempfile
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import rasterio
from osgeo import gdal, ogr, osr

from waterlagen._crs import same_crs
from waterlagen._downloads import stream_download_to_temp, validate_geopackage
from waterlagen.logger import get_logger

logger = get_logger(__name__)

SERVICE_URL = "https://basisinformatie-overstromingen.nl/geoserver/ows"
COVERAGE_ID = "LIWO_Basis__Overstromingsgevoelige_gebieden_grote_en_regionale_wateren"
FILENAME = "overstromingsgevoelige_gebieden_grote_en_regionale_wateren.tif"
OUTPUT_LAYER = "buitendijks_gebied_uit_liwo"
SELECTED_CLASSES = {
    1: "Buitendijks gebied (niet door primaire keringen beschermd)",
    6: "Extra overstroombaar gebied volgens regionaal onbeschermd",
}


def _validate_raster(path: Path, *, national: bool = False) -> None:
    """Reject styled images, changed grids, unknown classes and unreadable blocks."""
    with rasterio.open(path) as source:
        if source.driver != "GTiff" or source.count != 1 or source.dtypes != ("uint8",):
            raise ValueError(
                "LIWO requires a single-band uint8 GeoTIFF with class values"
            )
        if not same_crs(source.crs, "EPSG:28992") or source.res != (25, 25):
            raise ValueError(
                "LIWO requires its native EPSG:28992 grid at 25 m resolution"
            )
        if (
            source.transform.b != 0
            or source.transform.d != 0
            or source.transform.e >= 0
        ):
            raise ValueError("LIWO requires a north-up raster")
        if national and (
            (source.width, source.height) != (10921, 12523)
            or tuple(source.bounds) != (11825, 306750, 284850, 619825)
        ):
            raise ValueError(
                "LIWO coverage extent/grid changed; inspect service metadata"
            )
        for _, window in source.block_windows(1):
            values = source.read(1, window=window, masked=True).compressed()
            if np.any(values > 6):
                raise ValueError(
                    "Unexpected LIWO class value; inspect the service legend"
                )


def download_raster(
    target_path: Path,
    *,
    overwrite: bool = False,
    timeout: int = 300,
    progress: bool = True,
) -> Path:
    """Download and validate the national native-grid WCS coverage.

    Parameters
    ----------
    target_path : Path
        Destination GeoTIFF. Replacement is atomic after validation.
    overwrite : bool, optional
        Replace an existing raster. Otherwise validate and reuse it offline.
    timeout : int, optional
        HTTP timeout in seconds.
    progress : bool, optional
        Show named download progress.

    Returns
    -------
    Path
        Validated GeoTIFF path.
    """
    target_path = Path(target_path)
    if target_path.exists() and not overwrite:
        logger.info("Validating and reusing LIWO raster %s", target_path)
        _validate_raster(target_path, national=True)
        return target_path
    url = (
        SERVICE_URL
        + "?"
        + urlencode(
            {
                "service": "WCS",
                "version": "2.0.1",
                "request": "GetCoverage",
                "coverageId": COVERAGE_ID,
                "format": "image/tiff",
            }
        )
    )
    downloaded = stream_download_to_temp(
        url,
        target_path,
        suffix=".tif",
        timeout=timeout,
        progress=progress,
        logger=logger,
        description="LIWO overstromingsgevoelige gebieden",
    )
    temporary_path = downloaded.target_path
    try:
        logger.info("Validating LIWO raster %s", temporary_path)
        _validate_raster(temporary_path, national=True)
        temporary_path.replace(target_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    logger.info("LIWO raster available at %s", target_path)
    return target_path


def polygonize_selected(raster_path: Path, target_path: Path) -> Path:
    """Polygonize valid LIWO cells of classes 1 and 6 with four-cell connectivity.

    Parameters
    ----------
    raster_path : Path
        Single-band native-grid LIWO GeoTIFF, national or a subset.
    target_path : Path
        Output GeoPackage, atomically replaced after validation. The output
        retains EPSG:28992 and contains ``klasse`` and ``omschrijving`` fields.

    Returns
    -------
    Path
        GeoPackage containing only the selected classes. Adjacent classes stay
        separate; diagonal cells are not joined. No smoothing is applied.
    """
    raster_path, target_path = Path(raster_path), Path(target_path)
    if raster_path.resolve() == target_path.resolve():
        raise ValueError("Raster and polygon output paths must differ")
    _validate_raster(raster_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".liwo_", dir=target_path.parent
    ) as directory:
        mask_path = Path(directory) / "selection.tif"
        output_path = Path(directory) / "selection.gpkg"
        logger.info("Selecting LIWO classes 1 and 6 into %s", mask_path)
        with rasterio.open(raster_path) as source:
            profile = source.profile.copy()
            profile.update(
                dtype="uint8",
                count=1,
                nodata=0,
                compress="deflate",
                tiled=True,
                blockxsize=256,
                blockysize=256,
            )
            with rasterio.open(mask_path, "w", **profile) as mask:
                for _, window in source.block_windows(1):
                    values = source.read(1, window=window)
                    selected = np.isin(values, list(SELECTED_CLASSES))
                    selected &= source.read_masks(1, window=window) != 0
                    mask.write(selected.astype("uint8"), 1, window=window)
        logger.info("Polygonizing selected LIWO cells to %s", target_path)
        with (
            gdal.ExceptionMgr(),
            ogr.ExceptionMgr(),
            gdal.Open(str(raster_path)) as raster,
            gdal.Open(str(mask_path)) as mask,
            ogr.GetDriverByName("GPKG").CreateDataSource(str(output_path)) as output,
        ):
            crs = osr.SpatialReference()
            crs.ImportFromWkt(raster.GetProjection())
            layer = output.CreateLayer(OUTPUT_LAYER, srs=crs, geom_type=ogr.wkbPolygon)
            layer.CreateField(ogr.FieldDefn("klasse", ogr.OFTInteger))
            layer.CreateField(ogr.FieldDefn("omschrijving", ogr.OFTString))
            layer.SyncToDisk()
            gdal.Polygonize(raster.GetRasterBand(1), mask.GetRasterBand(1), layer, 0)
            for code, label in SELECTED_CLASSES.items():
                output.ExecuteSQL(
                    f"UPDATE {OUTPUT_LAYER} SET omschrijving = '{label}' WHERE klasse = {code}"
                )
            count = layer.GetFeatureCount()
            output.FlushCache()
            layer = None
        validate_geopackage(output_path)
        output_path.replace(target_path)
    logger.info("Completed LIWO selection: %s polygons in %s", count, target_path)
    return target_path
