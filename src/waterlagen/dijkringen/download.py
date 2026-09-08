from pathlib import Path
from urllib.parse import urlencode

import geopandas as gpd
import requests
from waterlagen import datastore
from waterlagen._downloads import (
    DownloadPayloadError,
    GeoPackageDownload,
    download_geopackage_with_metadata,
    stream_download_to_temp,
    validate_geopackage,
)
from waterlagen.logger import get_logger
from waterlagen.settings import settings

logger = get_logger(name=__name__)

DIJKRINGEN_URL = (
    "https://geo.rijkswaterstaat.nl/services/ogc/gdr/dijkringen_historie/ows"
    "?service=WFS&version=2.0.0&request=GetFeature"
    "&typeName=dijkring_v_2012&outputFormat=geopackage"
)
DEFAULT_FILENAME = "dijkringen_historie_2012.gpkg"
DIJKRINGEN_MAPSERVER_URL = (
    "https://geo.rijkswaterstaat.nl/arcgis/rest/services/GDR/"
    "dijkringen_historie/MapServer/2/query?"
    + urlencode(
        {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "28992",
            "f": "geojson",
        }
    )
)


def _download_from_mapserver(
    *, target_path: Path, progress: bool
) -> GeoPackageDownload:
    downloaded_file = stream_download_to_temp(
        url=DIJKRINGEN_MAPSERVER_URL,
        target_path=target_path,
        suffix=".geojson",
        description="dijkringen GeoJSON fallback",
        logger=logger,
        progress=progress,
    )
    temporary_gpkg = target_path.with_name(f".{target_path.name}.mapserver.gpkg")
    try:
        try:
            data = gpd.read_file(downloaded_file.target_path)
        except Exception as exc:
            raise DownloadPayloadError(
                "MapServer returned invalid dijkringen GeoJSON"
            ) from exc
        if data.empty:
            raise DownloadPayloadError("MapServer returned no dijkringen")
        if data.crs is None:
            data = data.set_crs(settings.crs)
        elif str(data.crs) != settings.crs:
            data = data.to_crs(settings.crs)
        data.to_file(temporary_gpkg, driver="GPKG", layer="dijkring_v_2012")
        validate_geopackage(temporary_gpkg)
        temporary_gpkg.replace(target_path)
        return GeoPackageDownload(
            source_url=DIJKRINGEN_MAPSERVER_URL,
            target_path=target_path,
            downloaded_bytes=downloaded_file.downloaded_bytes,
            total_size_known=downloaded_file.total_size_known,
            total_bytes=downloaded_file.total_bytes,
            content_type=downloaded_file.content_type,
        )
    finally:
        downloaded_file.target_path.unlink(missing_ok=True)
        temporary_gpkg.unlink(missing_ok=True)


def download_dijkringen(
    download_dir: Path = datastore.dijkringen_dir,
    *,
    target_path: Path | None = None,
    overwrite: bool = True,
    progress: bool = True,
) -> GeoPackageDownload:
    """Download the historical Rijkswaterstaat dike-ring GeoPackage."""
    if target_path is None:
        target_path = Path(download_dir) / DEFAULT_FILENAME
    else:
        target_path = Path(target_path)

    if target_path.exists() and not overwrite:
        return download_geopackage_with_metadata(
            url=DIJKRINGEN_URL,
            target_path=target_path,
            overwrite=False,
            logger=logger,
            progress=progress,
            expected_crs=settings.crs,
        )

    try:
        return download_geopackage_with_metadata(
            url=DIJKRINGEN_URL,
            target_path=target_path,
            overwrite=overwrite,
            logger=logger,
            progress=progress,
            expected_crs=settings.crs,
        )
    except requests.HTTPError as exc:
        logger.warning(
            "Dijkringen WFS download failed with %s; trying ArcGIS MapServer fallback",
            exc,
        )
        return _download_from_mapserver(target_path=target_path, progress=progress)


def download_dijkringen_historie(
    download_dir: Path = datastore.dijkringen_dir,
    *,
    target_path: Path | None = None,
    overwrite: bool = True,
    progress: bool = True,
) -> GeoPackageDownload:
    """Download the historical Rijkswaterstaat dike-ring GeoPackage."""
    return download_dijkringen(
        download_dir=download_dir,
        target_path=target_path,
        overwrite=overwrite,
        progress=progress,
    )
