from pathlib import Path

from waterlagen import datastore
from waterlagen._downloads import (
    GeoPackageDownload,
    download_geopackage_from_zip_with_metadata,
)
from waterlagen.logger import get_logger
from waterlagen.settings import settings

logger = get_logger(name=__name__)

HYDAMO_URL = "https://nhipackages.blob.core.windows.net/packages/gkw-hydamo-package.zip"
DEFAULT_FILENAME = "hydamo.gpkg"


def download_hydamo(
    download_dir: Path = datastore.hydamo_dir,
    *,
    target_path: Path | None = None,
    overwrite: bool = True,
    progress: bool = True,
    chunk_size: int = 1024 * 1024,
    timeout: int = 30,
) -> GeoPackageDownload:
    """Download the national GKW HYDAMO GeoPackage.

    The GKW distribution is a ZIP archive containing one GeoPackage. The archive
    is streamed to a temporary file, its GeoPackage member is validated, and the
    result is atomically moved to the target after validation. Spatial layers are
    kept in the configured project CRS.

    Parameters
    ----------
    download_dir : Path, optional
        Directory for the default output path, by default ``datastore.hydamo_dir``.
    target_path : Path, optional
        Output GeoPackage path. Defaults to ``download_dir / "hydamo.gpkg"``.
    overwrite : bool, optional
        Whether to replace an existing target. With False, the existing target is
        reused and no archive is downloaded.
    progress : bool, optional
        Whether to write named download progress to stdout.
    chunk_size : int, optional
        HTTP download chunk size in bytes.
    timeout : int, optional
        HTTP timeout in seconds.

    Returns
    -------
    GeoPackageDownload
        Output path and download metadata.
    """
    download_dir = Path(download_dir)
    if target_path is None:
        target_path = download_dir / DEFAULT_FILENAME
    else:
        target_path = Path(target_path)

    return download_geopackage_from_zip_with_metadata(
        url=HYDAMO_URL,
        target_path=target_path,
        overwrite=overwrite,
        chunk_size=chunk_size,
        timeout=timeout,
        logger=logger,
        progress=progress,
        description="GKW HYDAMO GeoPackage",
        expected_crs=settings.crs,
    )
