"""Cloud redirect, payload failures and safe offline source reuse."""

from unittest.mock import Mock
import importlib

import geopandas as gpd
import pytest
import requests
from shapely.geometry import LineString

from waterlagen._downloads import DownloadPayloadError
from waterlagen.rijkswateren import download_rijkswateren

module = importlib.import_module("waterlagen.rijkswateren.download")


class Response:
    def __init__(
        self,
        payload=b"",
        *,
        url="https://cloud.example/s/changing-token",
        status=200,
        length=None,
    ):
        self.payload = payload
        self.url = url
        self.status = status
        self.headers = {
            "Content-Length": str(len(payload) if length is None else length)
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(str(self.status))

    def iter_content(self, chunk_size):
        yield self.payload


@pytest.fixture
def payload(tmp_path):
    source = tmp_path / "source.gpkg"
    gpd.GeoDataFrame(
        {"nen3610id": ["NL.WBHCODE.80.x"], "categorieoppervlaktewater": ["primair"]},
        geometry=[LineString([(0, 0), (10, 10)])],
        crs=28992,
    ).to_file(source, layer="hydroobject")
    return source.read_bytes()


def test_redirect_file_selection_and_offline_reuse(tmp_path, monkeypatch, payload):
    get = Mock(side_effect=[Response(), Response(payload)])
    monkeypatch.setattr(requests, "get", get)
    result = download_rijkswateren(tmp_path, timeout=7, progress=False)
    assert result.read_bytes() == payload
    assert get.call_count == 2
    assert (
        get.call_args_list[1].args[0]
        == "https://cloud.example/s/changing-token/download?path=%2Fhydamo&files=rws_hydamo.gpkg"
    )
    assert all(call.kwargs["timeout"] == 7 for call in get.call_args_list)
    get.reset_mock(side_effect=True)
    assert download_rijkswateren(tmp_path, source_url="unreachable") == result
    get.assert_not_called()


@pytest.mark.parametrize(
    "response,error",
    [
        (Response(b"<html>share page</html>"), DownloadPayloadError),
        (Response(b"sqlite", length=100), DownloadPayloadError),
        (Response(status=404), requests.HTTPError),
        (Response(b"not a database"), DownloadPayloadError),
    ],
)
def test_failed_refresh_keeps_existing(tmp_path, monkeypatch, payload, response, error):
    target = tmp_path / "rws_hydamo.gpkg"
    target.write_bytes(payload)
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    with pytest.raises(error):
        download_rijkswateren(
            tmp_path,
            source_url="https://example.test/file.gpkg",
            overwrite=True,
            progress=False,
        )
    assert target.read_bytes() == payload
    assert not list(tmp_path.glob(".rws_hydamo.gpkg.*"))


def test_wrong_layer_preserves_existing(tmp_path, monkeypatch, payload):
    wrong = tmp_path / "wrong.gpkg"
    gpd.GeoDataFrame(geometry=[LineString([(0, 0), (1, 1)])], crs=28992).to_file(
        wrong, layer="wrong"
    )
    target = tmp_path / "rws_hydamo.gpkg"
    target.write_bytes(payload)
    monkeypatch.setattr(
        requests, "get", Mock(return_value=Response(wrong.read_bytes()))
    )
    with pytest.raises(ValueError):
        download_rijkswateren(
            tmp_path,
            source_url="https://example.test/file.gpkg",
            overwrite=True,
            progress=False,
        )
    assert target.read_bytes() == payload
