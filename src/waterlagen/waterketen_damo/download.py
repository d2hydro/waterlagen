from pathlib import Path

from waterlagen import datastore
from waterlagen._downloads import GeoPackageDownload, download_geopackage_with_metadata
from waterlagen.logger import get_logger
from waterlagen.settings import settings

logger = get_logger(__name__)

WATERKETEN_DAMO_URL = (
    "https://service.pdok.nl/hwh/waterschappen-waterketen-damo/atom/"
    "downloads/hwh_waterketen_geopackage_DAMO.gpkg"
)
DEFAULT_FILENAME = "waterketen_damo.gpkg"


def download_waterketen_damo(
    download_dir: Path | None = None,
    *,
    target_path: Path | None = None,
    overwrite: bool = True,
    progress: bool = True,
    chunk_size: int = 1024 * 1024,
    timeout: int = 30,
) -> GeoPackageDownload:
    """Download the current PDOK Waterketen DAMO GeoPackage.

    Use the GeoPackage endpoint published in the PDOK ATOM feed. New downloads
    are streamed to a temporary file beside the target, validated and brought
    into the configured project CRS before atomically replacing the target.

    Parameters
    ----------
    download_dir : Path, optional
        Source directory, defaulting to ``datastore.waterketen_damo_dir``.
    target_path : Path, optional
        Output path overriding ``download_dir / "waterketen_damo.gpkg"``.
    overwrite : bool, optional
        Replace an existing target, by default True. With False, reuse it
        without a network request or revalidation.
    progress : bool, optional
        Write named download progress to stdout, by default True.
    chunk_size : int, optional
        HTTP download chunk size in bytes, by default 1048576.
    timeout : int, optional
        HTTP timeout in seconds, by default 30.

    Returns
    -------
    GeoPackageDownload
        Output path and download metadata.

    Raises
    ------
    requests.HTTPError
        The server returns an unsuccessful HTTP status.
    waterlagen._downloads.DownloadPayloadError
        The response is incomplete or is not a valid GeoPackage.
    """
    if target_path is None:
        directory = (
            datastore.waterketen_damo_dir
            if download_dir is None
            else Path(download_dir)
        )
        target_path = directory / DEFAULT_FILENAME
    else:
        target_path = Path(target_path)

    if target_path.exists() and not overwrite:
        logger.info("Reusing Waterketen DAMO from %s", target_path)
    else:
        logger.info("Downloading Waterketen DAMO to %s", target_path)

    result = download_geopackage_with_metadata(
        url=WATERKETEN_DAMO_URL,
        target_path=target_path,
        overwrite=overwrite,
        progress=progress,
        chunk_size=chunk_size,
        timeout=timeout,
        logger=logger,
        description="Waterketen DAMO GeoPackage",
        expected_crs=settings.crs,
    )
    logger.info("Waterketen DAMO available at %s", result.target_path)
    return result
