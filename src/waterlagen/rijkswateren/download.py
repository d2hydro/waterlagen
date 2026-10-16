"""Retrieve one GeoPackage from the public Waterlagen cloud share."""

from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit
import re

import pyogrio
import requests

from waterlagen._downloads import stream_download_to_temp, validate_geopackage
from waterlagen._filesystem import replace_file
from waterlagen.datastore import DataStore
from waterlagen.logger import get_logger

logger = get_logger(__name__)
RIJKSWATEREN_URL = "https://waterlagen.d2hydro.nl"


def _download_url(source_url: str, timeout: float) -> str:
    """Resolve a public share without downloading its HTML as source data."""
    if urlsplit(source_url).path.lower().endswith(".gpkg"):
        return source_url
    with requests.get(source_url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        resolved = urlsplit(response.url)
    match = re.fullmatch(r"(.*?/s/[^/]+)/?", resolved.path)
    if match is None:
        raise ValueError(
            f"Expected a public Nextcloud share or GeoPackage URL: {source_url}"
        )
    return urlunsplit(
        (
            resolved.scheme,
            resolved.netloc,
            match[1] + "/download",
            urlencode({"path": "/hydamo", "files": "rws_hydamo.gpkg"}),
            "",
        )
    )


def _validate_source(path: Path) -> None:
    validate_geopackage(path)
    if "hydroobject" not in pyogrio.list_layers(path)[:, 0]:
        raise ValueError(f"Rijkswateren source is missing hydroobject: {path}")
    info = pyogrio.read_info(path, layer="hydroobject")
    if info["crs"] is None:
        raise ValueError(f"Rijkswateren hydroobject has no CRS: {path}")
    if not {"categorieoppwaterlichaam", "categorieoppervlaktewater"}.intersection(
        info["fields"]
    ):
        raise ValueError(f"Rijkswateren hydroobject has no category column: {path}")
    if "nen3610id" not in info["fields"]:
        raise ValueError(f"Rijkswateren hydroobject has no nen3610id: {path}")


def download_rijkswateren(
    download_dir: Path | None = None,
    *,
    source_url: str = RIJKSWATEREN_URL,
    overwrite: bool = False,
    timeout: float = 30,
    progress: bool = True,
) -> Path:
    """Download or reuse the published Rijkswateren GeoPackage atomically.

    Parameters
    ----------
    download_dir : pathlib.Path, optional
        Destination directory, default ``DataStore().hydamo_dir``.
    source_url : str, optional
        Redirect to a public Nextcloud share, share URL, or direct GeoPackage URL.
        Shares contain ``hydamo/rws_hydamo.gpkg``. No share token is configured.
    overwrite : bool, optional
        Refresh an existing source. Otherwise validate and reuse it offline.
    timeout : float, optional
        Timeout in seconds for each HTTP request.
    progress : bool, optional
        Show named byte progress for the GeoPackage download.

    Returns
    -------
    pathlib.Path
        Validated local source, preserving its original CRS. Source selection
        explicitly transforms geometries to the project CRS when reading.

    Raises
    ------
    ValueError
        Invalid payload, missing hydroobject layer, category, identifier or CRS.
    requests.HTTPError
        The share or file request failed. An existing source remains intact.
    """
    directory = (
        Path(download_dir) if download_dir is not None else DataStore().hydamo_dir
    )
    target = directory / "rws_hydamo.gpkg"
    if target.is_file() and not overwrite:
        _validate_source(target)
        logger.info("Reusing Rijkswateren source %s", target)
        return target
    url = _download_url(source_url, timeout)
    downloaded = stream_download_to_temp(
        url,
        target,
        timeout=timeout,
        progress=progress,
        logger=logger,
        description="Rijkswateren HyDAMO",
    )
    try:
        logger.info("Validating Rijkswateren source %s", downloaded.target_path)
        _validate_source(downloaded.target_path)
        replace_file(downloaded.target_path, target)
    finally:
        downloaded.target_path.unlink(missing_ok=True)
    logger.info("Completed Rijkswateren download to %s", target)
    return target
