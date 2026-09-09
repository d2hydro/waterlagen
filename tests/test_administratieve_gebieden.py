import logging
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from waterlagen._downloads import DownloadPayloadError, validate_geopackage
from waterlagen.administratieve_gebieden import (
    UNIFORM_AREA_COLUMNS,
    WATERSCHAPSGRENZEN_URL,
    download_bestuurlijke_gebieden,
    download_waterschapsgrenzen,
    normaliseer_bestuurlijke_gebieden,
    normaliseer_waterschapsgrenzen,
    read_landsgrens,
)
from waterlagen.administratieve_gebieden.download import bestuurlijke_gebieden_url
from waterlagen.administratieve_gebieden.sources import LANDSGRENS_LAYER


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


def _geopackage_bytes(path: Path) -> bytes:
    source_path = path / "source.gpkg"
    gdf = gpd.GeoDataFrame(
        {"naam": ["Nederland"], "code": ["6030"]},
        geometry=[box(100000, 400000, 101000, 401000)],
        crs="EPSG:28992",
    )
    gdf.to_file(source_path, layer=LANDSGRENS_LAYER, driver="GPKG")
    validate_geopackage(source_path)
    return source_path.read_bytes()


def _write_landsgrens(path: Path, *, crs: str = "EPSG:28992") -> None:
    gdf = gpd.GeoDataFrame(
        {"identificatie": ["LND6030"], "naam": ["Nederland"], "code": ["6030"]},
        geometry=[box(100000, 400000, 101000, 401000)],
        crs=crs,
    )
    gdf.to_file(path, layer=LANDSGRENS_LAYER, driver="GPKG")


def test_datastore_administratieve_gebieden_dir(tmp_path):
    from waterlagen.datastore import DataStore

    datastore = DataStore(data_dir=tmp_path / "data")

    assert (
        datastore.administratieve_gebieden_dir
        == tmp_path / "data" / "source_data" / "administratieve_gebieden"
    )
    assert datastore.administratieve_gebieden_dir.is_dir()


def test_download_bestuurlijke_gebieden_uses_requested_year_url(monkeypatch, tmp_path):
    payload = _geopackage_bytes(tmp_path)
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(payload)

    monkeypatch.setattr("waterlagen._downloads.requests.get", fake_get)

    result = download_bestuurlijke_gebieden(2024, download_dir=tmp_path, progress=False)

    assert result.target_path == tmp_path / "BestuurlijkeGebieden_2024.gpkg"
    assert calls[0][0] == bestuurlijke_gebieden_url(2024)
    validate_geopackage(result.target_path)


def test_download_waterschapsgrenzen_uses_configured_url(monkeypatch, tmp_path):
    payload = _geopackage_bytes(tmp_path)
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(payload)

    monkeypatch.setattr("waterlagen._downloads.requests.get", fake_get)

    result = download_waterschapsgrenzen(download_dir=tmp_path, progress=False)

    assert calls[0][0] == WATERSCHAPSGRENZEN_URL
    validate_geopackage(result.target_path)


def test_download_reuses_existing_geopackage_without_http_request(
    monkeypatch, tmp_path
):
    target = tmp_path / "BestuurlijkeGebieden_2026.gpkg"
    target.write_bytes(_geopackage_bytes(tmp_path))

    def fail_get(*args, **kwargs):
        raise AssertionError("download should not be requested")

    monkeypatch.setattr("waterlagen._downloads.requests.get", fail_get)

    result = download_bestuurlijke_gebieden(
        2026,
        target_path=target,
        overwrite=False,
        progress=False,
    )

    assert result.target_path == target
    assert result.downloaded_bytes == 0


def test_download_validates_before_replacing_existing_geopackage(monkeypatch, tmp_path):
    target = tmp_path / "BestuurlijkeGebieden_2026.gpkg"
    previous_payload = _geopackage_bytes(tmp_path)
    target.write_bytes(previous_payload)
    monkeypatch.setattr(
        "waterlagen._downloads.requests.get",
        lambda *args, **kwargs: FakeResponse(b"not a geopackage"),
    )

    with pytest.raises(DownloadPayloadError, match="not a valid GeoPackage"):
        download_bestuurlijke_gebieden(2026, target_path=target, progress=False)

    assert target.read_bytes() == previous_payload


def test_normaliseer_waterschapsgrenzen_parses_missing_waterbeheercode(caplog):
    gebieden = gpd.GeoDataFrame(
        {
            "naam": ["Waterschap Drents Overijsselse Delta"],
            "code": [None],
            "waterbeheerdercode": [None],
            "nen3610id": ["NL.WBHCODE.59.Admingrenswaterschap.5110986"],
        },
        geometry=[Point(0, 0)],
        crs="EPSG:28992",
    )
    caplog.set_level(
        logging.WARNING,
        logger="waterlagen.administratieve_gebieden.sources",
    )

    result = normaliseer_waterschapsgrenzen(gebieden)

    assert result.at[0, "waterbeheercode"] == "59"
    assert "parsed from NEN3610 ID" in caplog.text


def test_normaliseer_waterschapsgrenzen_warns_for_invalid_nen3610id(caplog):
    gebieden = gpd.GeoDataFrame(
        {
            "naam": ["Onbekend waterschap"],
            "code": [None],
            "waterbeheerdercode": [None],
            "nen3610id": ["geen-geldige-nen3610id"],
        },
        geometry=[Point(0, 0)],
        crs="EPSG:28992",
    )
    caplog.set_level(
        logging.WARNING,
        logger="waterlagen.administratieve_gebieden.sources",
    )

    result = normaliseer_waterschapsgrenzen(gebieden)

    assert result.at[0, "waterbeheercode"] is None
    assert "cannot be parsed" in caplog.text


def test_normaliseer_bestuurlijke_gebieden_has_uniform_model():
    gebieden = gpd.GeoDataFrame(
        {
            "identificatie": ["LND6030"],
            "naam": ["Nederland"],
            "code": ["6030"],
        },
        geometry=[Point(0, 0)],
        crs="EPSG:28992",
    )

    result = normaliseer_bestuurlijke_gebieden(gebieden, year=2026)

    assert set(UNIFORM_AREA_COLUMNS).issubset(result.columns)
    assert result.at[0, "naam"] == "Nederland"
    assert result.at[0, "bgt_code"] == "6030"
    assert result.at[0, "waterbeheercode"] is None
    assert result.at[0, "versie"] == "2026"
    assert result.geometry.iloc[0].equals(Point(0, 0))


def test_read_landsgrens_uses_landgebied_layer(tmp_path):
    source_path = tmp_path / "BestuurlijkeGebieden_2026.gpkg"
    _write_landsgrens(source_path)

    result = read_landsgrens(path=source_path)

    assert result.at[0, "naam"] == "Nederland"
    assert result.crs == "EPSG:28992"
