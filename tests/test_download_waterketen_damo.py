from importlib import import_module

import geopandas as gpd
import pytest
import requests
from shapely.geometry import Point

from waterlagen._downloads import DownloadPayloadError, validate_geopackage
from waterlagen.datastore import DataStore
from waterlagen.waterketen_damo import WATERKETEN_DAMO_URL, download_waterketen_damo


class FakeResponse:
    def __init__(self, payload, *, status=200, length=None):
        self.payload = payload
        self.status = status
        self.headers = {
            "Content-Length": str(len(payload) if length is None else length)
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(str(self.status))

    def iter_content(self, chunk_size):
        for start in range(0, len(self.payload), chunk_size):
            yield self.payload[start : start + chunk_size]


@pytest.fixture
def payload(tmp_path):
    path = tmp_path / "source.gpkg"
    gpd.GeoDataFrame(
        {"code": ["test"]}, geometry=[Point(120000, 450000)], crs="EPSG:28992"
    ).to_file(path, layer="rwzi", driver="GPKG")
    return path.read_bytes()


def test_download_default_datastore_and_options(monkeypatch, tmp_path, payload):
    store = DataStore(source_data_dir=tmp_path / "sources", data_dir=tmp_path)
    module = import_module("waterlagen.waterketen_damo.download")
    monkeypatch.setattr(module, "datastore", store)
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(payload)

    monkeypatch.setattr("waterlagen._downloads.requests.get", fake_get)
    result = download_waterketen_damo(progress=False, timeout=17, chunk_size=8192)
    assert store.waterketen_damo_dir == tmp_path / "sources" / "waterketen_damo"
    assert result.target_path == store.waterketen_damo_dir / "waterketen_damo.gpkg"
    assert calls == [
        (WATERKETEN_DAMO_URL, {"stream": True, "allow_redirects": True, "timeout": 17})
    ]
    assert result.downloaded_bytes == len(payload)
    validate_geopackage(result.target_path)
    assert gpd.read_file(result.target_path, layer="rwzi").iloc[0]["code"] == "test"


@pytest.mark.parametrize("explicit_target", [False, True])
def test_output_overrides_and_offline_reuse(
    monkeypatch, tmp_path, payload, explicit_target
):
    monkeypatch.setattr(
        "waterlagen._downloads.requests.get",
        lambda *args, **kwargs: FakeResponse(payload),
    )
    kwargs = {"download_dir": tmp_path / "download"}
    expected = tmp_path / "download" / "waterketen_damo.gpkg"
    if explicit_target:
        expected = tmp_path / "custom" / "source.gpkg"
        kwargs["target_path"] = expected
    result = download_waterketen_damo(**kwargs, progress=False)
    assert result.target_path == expected
    previous = expected.read_bytes()

    def fail_get(*args, **kwargs):
        raise AssertionError("No network request expected")

    monkeypatch.setattr("waterlagen._downloads.requests.get", fail_get)
    result = download_waterketen_damo(**kwargs, overwrite=False, progress=False)
    assert result.downloaded_bytes == 0
    assert expected.read_bytes() == previous


@pytest.mark.parametrize("failure", ["invalid", "incomplete", "http"])
def test_failed_download_preserves_existing_file(
    monkeypatch, tmp_path, payload, failure
):
    target = tmp_path / "target.gpkg"
    target.write_bytes(payload)
    response = FakeResponse(b"invalid")
    error = DownloadPayloadError
    if failure == "incomplete":
        response = FakeResponse(payload, length=len(payload) + 100)
    elif failure == "http":
        response = FakeResponse(b"", status=503)
        error = requests.HTTPError
    monkeypatch.setattr(
        "waterlagen._downloads.requests.get", lambda *args, **kwargs: response
    )
    with pytest.raises(error):
        download_waterketen_damo(target_path=target, progress=False)
    assert target.read_bytes() == payload
    assert not list(tmp_path.glob(".target.gpkg.*"))


def test_download_uses_configured_crs(monkeypatch, tmp_path, payload):
    module = import_module("waterlagen.waterketen_damo.download")
    monkeypatch.setattr(module.settings, "crs", "EPSG:4326")
    monkeypatch.setattr(
        "waterlagen._downloads.requests.get",
        lambda *args, **kwargs: FakeResponse(payload),
    )
    result = download_waterketen_damo(download_dir=tmp_path / "output", progress=False)
    data = gpd.read_file(result.target_path, layer="rwzi")
    assert data.crs.to_epsg() == 4326
    assert 3 < data.geometry.iloc[0].x < 8
