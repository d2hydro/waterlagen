import json
import os
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import geopandas as gpd
import requests

from waterlagen._crs import ensure_dataset_crs


class DownloadPayloadError(ValueError):
    """Raised when a downloaded payload is not the expected file type."""


class GeoServerExceptionError(DownloadPayloadError):
    """Raised when a downloaded payload contains an OGC/GeoServer exception."""


@dataclass(frozen=True)
class GeoPackageDownload:
    """Metadata for a streamed GeoPackage download."""

    source_url: str
    target_path: Path
    downloaded_bytes: int
    total_size_known: bool
    total_bytes: int | None = None
    content_type: str | None = None


@dataclass(frozen=True)
class FileDownload:
    """Metadata for a streamed file download."""

    source_url: str
    target_path: Path
    downloaded_bytes: int
    total_size_known: bool
    total_bytes: int | None = None
    content_type: str | None = None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _extract_ogc_exception_message(payload: bytes) -> str | None:
    stripped = payload.lstrip()
    if not stripped.startswith(b"<"):
        return None

    try:
        root = ElementTree.fromstring(stripped)
    except ElementTree.ParseError:
        return None

    root_name = _local_name(root.tag).lower()
    if "exception" not in root_name:
        return None

    messages: list[str] = []
    for element in root.iter():
        name = _local_name(element.tag).lower()
        if name in {"exceptiontext", "serviceexception"} and element.text:
            messages.append(element.text.strip())
        if name == "exception":
            for key in ("exceptionCode", "code", "locator"):
                value = element.get(key)
                if value:
                    messages.append(value.strip())

    message = "; ".join(dict.fromkeys(part for part in messages if part))
    return message or "GeoServer returned an OGC exception document"


def _raise_for_known_error_payload(
    path: Path, *, content_type: str | None = None
) -> None:
    with path.open("rb") as f:
        payload_start = f.read(65536)
    stripped = payload_start.lstrip()
    ogc_message = _extract_ogc_exception_message(payload_start)
    if ogc_message:
        raise GeoServerExceptionError(
            f"GeoServer returned an OGC exception: {ogc_message}"
        )

    content_type = (content_type or "").lower()
    if stripped.startswith(b"<"):
        if b"<html" in stripped[:512].lower() or "html" in content_type:
            raise DownloadPayloadError("Downloaded payload is an HTML error document")
        if "xml" in content_type:
            raise DownloadPayloadError("Downloaded payload is an XML error document")
        try:
            root = ElementTree.fromstring(stripped)
        except ElementTree.ParseError:
            return
        root_name = _local_name(root.tag).lower()
        if root_name in {"html", "error", "exception", "exceptionreport"}:
            raise DownloadPayloadError(
                "Downloaded payload is an XML/HTML error document"
            )

    if stripped.startswith((b"{", b"[")) or "json" in content_type:
        try:
            payload = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
            return
        raise DownloadPayloadError("Downloaded payload is a JSON error document")


def validate_geopackage(gpkg_path: Path) -> None:
    """Validate that a path is a readable GeoPackage with at least one layer."""
    gpkg_path = Path(gpkg_path)
    _raise_for_known_error_payload(gpkg_path)
    try:
        layers = gpd.list_layers(gpkg_path)
    except Exception as exc:
        raise DownloadPayloadError(f"{gpkg_path} is not a valid GeoPackage") from exc

    if layers.empty:
        raise DownloadPayloadError(
            f"{gpkg_path} is not a valid GeoPackage: no layers found"
        )


def _format_progress(downloaded: int, total: int | None) -> str:
    downloaded_mb = downloaded / 1024 / 1024
    if total is None:
        return f"{downloaded_mb:.1f} MB"

    total_mb = total / 1024 / 1024
    percent = downloaded / total * 100
    return f"{downloaded_mb:.1f} / {total_mb:.1f} MB ({percent:.1f}%)"


def _parse_content_length(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        total = int(value)
    except ValueError:
        return None
    return total if total > 0 else None


def stream_download_to_temp(
    url: str,
    target_path: Path,
    *,
    suffix: str | None = None,
    description: str | None = None,
    chunk_size: int = 1024 * 1024,
    timeout: int = 30,
    logger=None,
    progress: bool = True,
) -> FileDownload:
    """Stream a download to a temporary file beside target_path."""
    target_path = Path(target_path)
    target_path.parent.mkdir(exist_ok=True, parents=True)
    description = description or target_path.name

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=suffix or target_path.suffix,
        dir=target_path.parent,
    )
    tmp_path = Path(tmp_name)
    downloaded = 0
    total: int | None = None
    content_type: str | None = None
    try:
        if logger is not None:
            logger.info("Downloading %s to %s", description, target_path)

        with os.fdopen(fd, "wb") as f:
            with requests.get(
                url, stream=True, allow_redirects=True, timeout=timeout
            ) as response:
                response.raise_for_status()

                content_type = response.headers.get("Content-Type")
                total = _parse_content_length(response.headers.get("Content-Length"))

                for chunk in response.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue

                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress_text = _format_progress(downloaded, total)
                        sys.stdout.write(f"\r{description}: {progress_text}")
                        sys.stdout.flush()

        _raise_for_known_error_payload(tmp_path, content_type=content_type)
        return FileDownload(
            source_url=url,
            target_path=tmp_path,
            downloaded_bytes=downloaded,
            total_size_known=total is not None,
            total_bytes=total,
            content_type=content_type,
        )
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def download_geopackage_with_metadata(
    url: str,
    target_path: Path,
    *,
    overwrite: bool = True,
    chunk_size: int = 1024 * 1024,
    timeout: int = 30,
    logger=None,
    progress: bool = True,
    description: str | None = None,
    expected_crs: str | int | None = None,
) -> GeoPackageDownload:
    """Stream a GeoPackage download to a temp file and atomically replace target."""
    target_path = Path(target_path)
    target_path.parent.mkdir(exist_ok=True, parents=True)

    if target_path.exists() and not overwrite:
        return GeoPackageDownload(
            source_url=url,
            target_path=target_path,
            downloaded_bytes=0,
            total_size_known=False,
        )

    tmp_path: Path | None = None
    try:
        downloaded_file = stream_download_to_temp(
            url=url,
            target_path=target_path,
            suffix=".gpkg",
            chunk_size=chunk_size,
            timeout=timeout,
            logger=logger,
            progress=progress,
            description=description,
        )
        tmp_path = downloaded_file.target_path

        validate_geopackage(tmp_path)
        if expected_crs is not None:
            ensure_dataset_crs(tmp_path, expected_crs=expected_crs, logger=logger)
            validate_geopackage(tmp_path)
        tmp_path.replace(target_path)
        tmp_path = None
        return GeoPackageDownload(
            source_url=url,
            target_path=target_path,
            downloaded_bytes=downloaded_file.downloaded_bytes,
            total_size_known=downloaded_file.total_size_known,
            total_bytes=downloaded_file.total_bytes,
            content_type=downloaded_file.content_type,
        )

    except DownloadPayloadError as exc:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        if isinstance(exc, GeoServerExceptionError):
            raise
        raise DownloadPayloadError(f"{target_path} is not a valid GeoPackage") from exc
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise


def download_geopackage(
    url: str,
    target_path: Path,
    *,
    overwrite: bool = True,
    chunk_size: int = 1024 * 1024,
    timeout: int = 30,
    logger=None,
    progress: bool = True,
    description: str | None = None,
    expected_crs: str | int | None = None,
) -> Path:
    """Stream a GeoPackage download to a temp file and atomically replace target."""
    return download_geopackage_with_metadata(
        url=url,
        target_path=target_path,
        overwrite=overwrite,
        chunk_size=chunk_size,
        timeout=timeout,
        logger=logger,
        progress=progress,
        description=description,
        expected_crs=expected_crs,
    ).target_path


def _temporary_path(target_path: Path, *, suffix: str) -> Path:
    """Create an unused temporary path beside target_path."""
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=suffix,
        dir=target_path.parent,
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    tmp_path.unlink(missing_ok=True)
    return tmp_path


def _geopackage_member_from_zip(
    archive: zipfile.ZipFile,
    archive_path: Path,
    *,
    member_name: str | None,
) -> zipfile.ZipInfo:
    """Return the requested or sole GeoPackage member from a ZIP archive."""
    if member_name is not None:
        try:
            member = archive.getinfo(member_name)
        except KeyError as exc:
            raise DownloadPayloadError(
                f"{archive_path} does not contain GeoPackage member {member_name}"
            ) from exc
        if member.is_dir() or not member.filename.lower().endswith(".gpkg"):
            raise DownloadPayloadError(
                f"{archive_path} member {member_name} is not a GeoPackage"
            )
        return member

    geopackage_members = [
        member
        for member in archive.infolist()
        if not member.is_dir() and member.filename.lower().endswith(".gpkg")
    ]
    if not geopackage_members:
        raise DownloadPayloadError(f"{archive_path} does not contain a GeoPackage")
    if len(geopackage_members) > 1:
        names = ", ".join(member.filename for member in geopackage_members)
        raise DownloadPayloadError(
            f"{archive_path} contains multiple GeoPackages; select one explicitly: {names}"
        )
    return geopackage_members[0]


def download_geopackage_from_zip_with_metadata(
    url: str,
    target_path: Path,
    *,
    overwrite: bool = True,
    member_name: str | None = None,
    chunk_size: int = 1024 * 1024,
    timeout: int = 30,
    logger=None,
    progress: bool = True,
    description: str | None = None,
    expected_crs: str | int | None = None,
) -> GeoPackageDownload:
    """Download a ZIP archive, validate its GeoPackage member, and replace target.

    Parameters
    ----------
    url : str
        URL of the ZIP archive.
    target_path : Path
        GeoPackage output path. The completed, validated member replaces this path
        atomically.
    overwrite : bool, optional
        Whether to replace an existing target. When False, the existing target is
        returned without making an HTTP request.
    member_name : str, optional
        Exact GeoPackage member in the archive. When omitted, the archive must
        contain exactly one GeoPackage member.
    chunk_size : int, optional
        HTTP download chunk size in bytes.
    timeout : int, optional
        HTTP timeout in seconds.
    logger : logging.Logger, optional
        Logger for normal download, extraction, and validation progress.
    progress : bool, optional
        Whether to write named byte progress to stdout.
    description : str, optional
        Human-readable download label. Defaults to the target filename.
    expected_crs : str | int, optional
        CRS required for spatial layers. Layers with another defined CRS are
        reprojected before the target is replaced.

    Returns
    -------
    GeoPackageDownload
        Metadata for the downloaded GeoPackage. Invalid ZIP files, invalid
        GeoPackage members, and failed validation leave an existing target intact.
    """
    target_path = Path(target_path)
    target_path.parent.mkdir(exist_ok=True, parents=True)
    if target_path.exists() and not overwrite:
        if logger is not None:
            logger.info("Reusing existing GeoPackage %s", target_path)
        return GeoPackageDownload(
            source_url=url,
            target_path=target_path,
            downloaded_bytes=0,
            total_size_known=False,
        )

    archive_path: Path | None = None
    temporary_gpkg: Path | None = None
    try:
        downloaded_file = stream_download_to_temp(
            url=url,
            target_path=target_path,
            suffix=".zip",
            description=description,
            chunk_size=chunk_size,
            timeout=timeout,
            logger=logger,
            progress=progress,
        )
        archive_path = downloaded_file.target_path
        temporary_gpkg = _temporary_path(target_path, suffix=".gpkg")

        try:
            with zipfile.ZipFile(archive_path) as archive:
                member = _geopackage_member_from_zip(
                    archive,
                    archive_path,
                    member_name=member_name,
                )
                if logger is not None:
                    logger.info(
                        "Extracting GeoPackage member %s from %s",
                        member.filename,
                        archive_path,
                    )
                with (
                    archive.open(member) as source,
                    temporary_gpkg.open("wb") as target,
                ):
                    shutil.copyfileobj(source, target, length=chunk_size)
        except (OSError, zipfile.BadZipFile) as exc:
            raise DownloadPayloadError(
                f"{archive_path} is not a valid ZIP archive containing a GeoPackage"
            ) from exc

        if logger is not None:
            logger.info("Validating extracted GeoPackage %s", temporary_gpkg)
        validate_geopackage(temporary_gpkg)
        if expected_crs is not None:
            ensure_dataset_crs(
                temporary_gpkg,
                expected_crs=expected_crs,
                logger=logger,
            )
            validate_geopackage(temporary_gpkg)

        temporary_gpkg.replace(target_path)
        temporary_gpkg = None
        if logger is not None:
            logger.info(
                "Completed %s download to %s",
                description or target_path.name,
                target_path,
            )
        return GeoPackageDownload(
            source_url=url,
            target_path=target_path,
            downloaded_bytes=downloaded_file.downloaded_bytes,
            total_size_known=downloaded_file.total_size_known,
            total_bytes=downloaded_file.total_bytes,
            content_type=downloaded_file.content_type,
        )
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
        if temporary_gpkg is not None:
            temporary_gpkg.unlink(missing_ok=True)
