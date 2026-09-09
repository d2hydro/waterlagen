from pathlib import Path

from waterlagen import datastore
from waterlagen._downloads import GeoPackageDownload, download_geopackage_with_metadata
from waterlagen.logger import get_logger
from waterlagen.settings import settings

logger = get_logger(name=__name__)

BESTUURLIJKE_GEBIEDEN_URL = (
    "https://service.pdok.nl/kadaster/brk-bestuurlijke-gebieden/atom/downloads/"
    "BestuurlijkeGebieden_{year}.gpkg"
)
WATERSCHAPSGRENZEN_URL = (
    "https://service.pdok.nl/hwh/waterschappen-waterschapsgrenzen-imso/atom/"
    "downloads/hwh_waterschapsgrenzenimso_geopackage_IMWA.gpkg"
)
DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR = 2026
WATERSCHAPSGRENZEN_FILENAME = "hwh_waterschapsgrenzenimso_geopackage_IMWA.gpkg"


def _validate_year(year: int) -> None:
    """Validate that a requested administrative-boundary year is plausible."""
    if not isinstance(year, int) or isinstance(year, bool):
        raise TypeError("year must be an integer")
    if year < 1900:
        raise ValueError("year must be 1900 or later")


def bestuurlijke_gebieden_url(year: int) -> str:
    """Return the versioned PDOK GeoPackage URL for a selected year."""
    _validate_year(year)
    return BESTUURLIJKE_GEBIEDEN_URL.format(year=year)


def bestuurlijke_gebieden_path(
    year: int,
    download_dir: Path = datastore.administratieve_gebieden_dir,
) -> Path:
    """Return the datastore path for one bestuurlijke gebieden year."""
    _validate_year(year)
    return Path(download_dir) / f"BestuurlijkeGebieden_{year}.gpkg"


def download_bestuurlijke_gebieden(
    year: int,
    download_dir: Path = datastore.administratieve_gebieden_dir,
    *,
    target_path: Path | None = None,
    overwrite: bool = True,
    progress: bool = True,
    chunk_size: int = 1024 * 1024,
    timeout: int = 30,
) -> GeoPackageDownload:
    """Download a selected yearly PDOK bestuurlijke gebieden GeoPackage.

    The year is part of both the URL and output filename, so multiple annual
    releases can coexist in the datastore. The download is streamed to a
    temporary file and validated before it atomically replaces the target.

    Parameters
    ----------
    year : int
        Explicit PDOK release year. The standard tile workflow uses 2026.
    download_dir : Path, optional
        Directory for yearly source GeoPackages, by default
        ``datastore.administratieve_gebieden_dir``.
    target_path : Path, optional
        Override for the output GeoPackage path.
    overwrite : bool, optional
        Whether to replace an existing target. When False, the existing file is
        reused without a network request.
    progress : bool, optional
        Whether to write named download progress to stdout.
    chunk_size : int, optional
        HTTP download chunk size in bytes.
    timeout : int, optional
        HTTP timeout in seconds.

    Returns
    -------
    GeoPackageDownload
        Download metadata and the validated output path.
    """
    _validate_year(year)
    if target_path is None:
        target_path = bestuurlijke_gebieden_path(year, download_dir=download_dir)
    else:
        target_path = Path(target_path)

    if target_path.exists() and not overwrite:
        logger.info(
            "Reusing bestuurlijke gebieden %s from %s",
            year,
            target_path,
        )
    else:
        logger.info(
            "Downloading bestuurlijke gebieden version %s to %s",
            year,
            target_path,
        )

    return download_geopackage_with_metadata(
        url=bestuurlijke_gebieden_url(year),
        target_path=target_path,
        overwrite=overwrite,
        chunk_size=chunk_size,
        timeout=timeout,
        logger=logger,
        progress=progress,
        description=f"bestuurlijke gebieden {year}",
        expected_crs=settings.crs,
    )


def download_waterschapsgrenzen(
    download_dir: Path = datastore.administratieve_gebieden_dir,
    *,
    target_path: Path | None = None,
    overwrite: bool = True,
    progress: bool = True,
    chunk_size: int = 1024 * 1024,
    timeout: int = 30,
) -> GeoPackageDownload:
    """Download the current HWH waterschapsgrenzen GeoPackage.

    The HWH source is not distributed as yearly releases. The current IMWA
    GeoPackage is downloaded to the administrative-areas datastore directory,
    validated, and atomically replaces the target only after successful
    validation.

    Parameters
    ----------
    download_dir : Path, optional
        Directory for the waterschapsgrenzen source GeoPackage, by default
        ``datastore.administratieve_gebieden_dir``.
    target_path : Path, optional
        Override for the output GeoPackage path.
    overwrite : bool, optional
        Whether to replace an existing target. When False, the existing file is
        reused without a network request.
    progress : bool, optional
        Whether to write named download progress to stdout.
    chunk_size : int, optional
        HTTP download chunk size in bytes.
    timeout : int, optional
        HTTP timeout in seconds.

    Returns
    -------
    GeoPackageDownload
        Download metadata and the validated output path.
    """
    if target_path is None:
        target_path = Path(download_dir) / WATERSCHAPSGRENZEN_FILENAME
    else:
        target_path = Path(target_path)

    if target_path.exists() and not overwrite:
        logger.info("Reusing waterschapsgrenzen from %s", target_path)
    else:
        logger.info("Downloading waterschapsgrenzen to %s", target_path)

    return download_geopackage_with_metadata(
        url=WATERSCHAPSGRENZEN_URL,
        target_path=target_path,
        overwrite=overwrite,
        chunk_size=chunk_size,
        timeout=timeout,
        logger=logger,
        progress=progress,
        description="waterschapsgrenzen",
        expected_crs=settings.crs,
    )
