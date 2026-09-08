import io
import logging
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from waterlagen._downloads import DownloadPayloadError, validate_geopackage
from waterlagen.hydamo import HYDAMO_URL, download_hydamo


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size: int):
        yield self.payload


def _valid_geopackage_bytes(path: Path) -> bytes:
    geopackage_path = path / "source.gpkg"
    data = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[Point(120000, 480000)],
        crs="EPSG:28992",
    )
    data.to_file(geopackage_path, driver="GPKG", layer="hydroobject")
    return geopackage_path.read_bytes()


def _zip_with_geopackage(payload: bytes, *, member_name: str = "hydamo.gpkg") -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(member_name, payload)
    return archive.getvalue()


def _temporary_files(target: Path) -> list[Path]:
    return list(target.parent.glob(f".{target.name}.*"))


def test_download_hydamo_extracts_valid_geopackage(monkeypatch, tmp_path, caplog):
    payload = _zip_with_geopackage(_valid_geopackage_bytes(tmp_path))
    requests = []

    def fake_get(url, **kwargs):
        requests.append((url, kwargs))
        return FakeResponse(payload)

    monkeypatch.setattr("waterlagen._downloads.requests.get", fake_get)
    caplog.set_level(logging.INFO, logger="waterlagen.hydamo.download")

    result = download_hydamo(download_dir=tmp_path, progress=False)

    assert result.target_path == tmp_path / "hydamo.gpkg"
    assert result.source_url == HYDAMO_URL
    assert result.downloaded_bytes == len(payload)
    validate_geopackage(result.target_path)
    assert gpd.list_layers(result.target_path).iloc[0]["name"] == "hydroobject"
    assert _temporary_files(result.target_path) == []
    assert requests == [
        (
            HYDAMO_URL,
            {"stream": True, "allow_redirects": True, "timeout": 30},
        )
    ]
    assert "Downloading GKW HYDAMO GeoPackage to" in caplog.text
    assert "Extracting GeoPackage member hydamo.gpkg" in caplog.text
    assert "Validating extracted GeoPackage" in caplog.text
    assert "Completed GKW HYDAMO GeoPackage download" in caplog.text


def test_download_hydamo_reuses_existing_target_when_not_overwriting(
    monkeypatch, tmp_path
):
    target = tmp_path / "hydamo.gpkg"
    target.write_bytes(_valid_geopackage_bytes(tmp_path))

    def fail_get(*args, **kwargs):
        raise AssertionError("download should not be requested")

    monkeypatch.setattr("waterlagen._downloads.requests.get", fail_get)

    result = download_hydamo(target_path=target, overwrite=False, progress=False)

    assert result.target_path == target
    assert result.downloaded_bytes == 0
    validate_geopackage(target)


def test_download_hydamo_rejects_invalid_archive_without_replacing_target(
    monkeypatch, tmp_path
):
    target = tmp_path / "hydamo.gpkg"
    previous_payload = _valid_geopackage_bytes(tmp_path)
    target.write_bytes(previous_payload)

    monkeypatch.setattr(
        "waterlagen._downloads.requests.get",
        lambda *args, **kwargs: FakeResponse(b"not a zip archive"),
    )

    with pytest.raises(DownloadPayloadError, match="not a valid ZIP archive"):
        download_hydamo(target_path=target, progress=False)

    assert target.read_bytes() == previous_payload
    assert _temporary_files(target) == []


def test_download_hydamo_progress_identifies_download(monkeypatch, tmp_path, capsys):
    payload = _zip_with_geopackage(_valid_geopackage_bytes(tmp_path))
    monkeypatch.setattr(
        "waterlagen._downloads.requests.get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    download_hydamo(download_dir=tmp_path)

    assert "GKW HYDAMO GeoPackage:" in capsys.readouterr().out
