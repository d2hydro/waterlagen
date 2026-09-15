import io
import json
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from waterlagen.administratieve_gebieden import (
    CBS_BUURTCODE_COLUMN,
    CBS_BUURTEN_LAYER,
    CBS_WIJK_BUURTKAART_2025_URL,
    download_wijk_buurtkaart_2025,
)
from waterlagen.cbs import (
    CBS_KERNCIJFERS_2025_TABLE,
    CBS_STATLINE_CODES_URL,
    CBS_STATLINE_OBSERVATIONS_URL,
    BUURTGEGEVENS_COLUMNS,
    download_buurtgegevens_2025,
    read_buurtgegevens,
    validate_buurtcode_systematiek,
)


class JsonResponse:
    def __init__(self, payload: dict[str, object], url: str):
        self._payload = payload
        self.url = url

    def raise_for_status(self):
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class DownloadResponse:
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


def _buurten_geopackage(path: Path, codes: list[str]) -> Path:
    geopackage_path = path / "buurten.gpkg"
    buurten = gpd.GeoDataFrame(
        {CBS_BUURTCODE_COLUMN: codes},
        geometry=[Point(index, index) for index in range(len(codes))],
        crs="EPSG:28992",
    )
    buurten.to_file(geopackage_path, layer=CBS_BUURTEN_LAYER, driver="GPKG")
    return geopackage_path


def _wijk_buurtkaart_zip(path: Path) -> bytes:
    geopackage_path = _buurten_geopackage(path, ["BU00000001"])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.write(
            geopackage_path,
            "WijkBuurtkaart_2025_v1/wijkenbuurten_2025_v1.gpkg",
        )
    return buffer.getvalue()


def test_download_wijk_buurtkaart_uses_official_cbs_zip(monkeypatch, tmp_path):
    payload = _wijk_buurtkaart_zip(tmp_path)
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return DownloadResponse(payload)

    monkeypatch.setattr("waterlagen._downloads.requests.get", fake_get)

    result = download_wijk_buurtkaart_2025(download_dir=tmp_path, progress=False)

    assert calls[0][0] == CBS_WIJK_BUURTKAART_2025_URL
    assert result.target_path.exists()
    buurten = gpd.read_file(result.target_path, layer=CBS_BUURTEN_LAYER)
    assert buurten["buurtcode"].tolist() == ["BU00000001"]


def test_download_buurtgegevens_selects_only_buurten_and_requested_measures(
    monkeypatch, tmp_path
):
    calls = []
    responses = {
        CBS_STATLINE_CODES_URL: {
            "value": [{"Identifier": "BU00000001"}, {"Identifier": "BU00000002"}]
        },
        CBS_STATLINE_OBSERVATIONS_URL: {
            "value": [
                {
                    "Measure": "T001036",
                    "Value": 100,
                    "ValueAttribute": "None",
                    "WijkenEnBuurten": "BU00000001",
                },
                {
                    "Measure": "1050010_2",
                    "Value": 50,
                    "ValueAttribute": "None",
                    "WijkenEnBuurten": "BU00000001",
                },
                {
                    "Measure": "A018943_2",
                    "Value": None,
                    "ValueAttribute": ".",
                    "WijkenEnBuurten": "BU00000001",
                },
                {
                    "Measure": "T001036",
                    "Value": 200,
                    "ValueAttribute": "None",
                    "WijkenEnBuurten": "BU00000002",
                },
                {
                    "Measure": "1050010_2",
                    "Value": 90,
                    "ValueAttribute": "None",
                    "WijkenEnBuurten": "BU00000002",
                },
                {
                    "Measure": "A018943_2",
                    "Value": 110,
                    "ValueAttribute": "None",
                    "WijkenEnBuurten": "BU00000002",
                },
            ]
        },
    }

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return JsonResponse(responses[url], url)

    monkeypatch.setattr("waterlagen.cbs.buurtgegevens.requests.get", fake_get)

    result = download_buurtgegevens_2025(download_dir=tmp_path)

    assert result.buurt_count == 2
    assert result.table_identifier == CBS_KERNCIJFERS_2025_TABLE
    code_params = calls[0][1]["params"]
    assert code_params["$filter"] == "startswith(Identifier, 'BU')"
    observation_params = calls[1][1]["params"]
    assert "startswith(WijkenEnBuurten, 'BU')" in observation_params["$filter"]
    assert (
        observation_params["$select"] == "Measure,Value,ValueAttribute,WijkenEnBuurten"
    )

    payload = json.loads(result.target_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["columns"] == list(BUURTGEGEVENS_COLUMNS)
    assert payload["metadata"]["buurt_count"] == 2
    assert payload["rows"] == [
        {
            "buurtcode": "BU00000001",
            "aantal_inwoners": 100,
            "aantal_huishoudens": 50,
            "personenautos_totaal": None,
        },
        {
            "buurtcode": "BU00000002",
            "aantal_inwoners": 200,
            "aantal_huishoudens": 90,
            "personenautos_totaal": 110,
        },
    ]
    assert payload["metadata"]["cbs_value_attributes"] == {
        "BU00000001": {"personenautos_totaal": "."}
    }


def test_download_buurtgegevens_reuses_existing_result(monkeypatch, tmp_path):
    target_path = tmp_path / "buurtgegevens_2025.json"
    target_path.write_text('{"rows": [{"buurtcode": "BU00000001"}]}', encoding="utf-8")

    def fail_get(*args, **kwargs):
        raise AssertionError("CBS StatLine should not be requested")

    monkeypatch.setattr("waterlagen.cbs.buurtgegevens.requests.get", fail_get)

    result = download_buurtgegevens_2025(target_path=target_path, overwrite=False)

    assert result.reused is True
    assert result.buurt_count == 1


def test_read_buurtgegevens_keeps_selected_missing_values(tmp_path):
    path = tmp_path / "buurtgegevens_2025.json"
    path.write_text(
        json.dumps(
            {
                "rows": [
                    {"buurtcode": "BU00000001", "personenautos_totaal": None},
                    {"buurtcode": "BU00000002", "personenautos_totaal": 10},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = read_buurtgegevens(path, columns=("personenautos_totaal",))

    assert result["buurtcode"].tolist() == ["BU00000001", "BU00000002"]
    assert pd.isna(result.loc[0, "personenautos_totaal"])
    assert result.loc[1, "personenautos_totaal"] == 10


def test_validate_buurtcode_systematiek_requires_matching_unique_codes(tmp_path):
    buurtkaart_path = _buurten_geopackage(
        tmp_path,
        ["BU00000001", "BU00000002"],
    )
    buurtgegevens_path = tmp_path / "buurtgegevens_2025.json"
    buurtgegevens_path.write_text(
        json.dumps(
            {
                "rows": [
                    {"buurtcode": "BU00000001"},
                    {"buurtcode": "BU00000002"},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = validate_buurtcode_systematiek(buurtkaart_path, buurtgegevens_path)

    assert result.geometry_buurt_count == 2
    assert result.statline_buurt_count == 2
    assert result.geometry_codes_without_statline == 0

    buurtgegevens_path.write_text(
        json.dumps({"rows": [{"buurtcode": "BU99999999"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="absent from CBS buurtgeometrie"):
        validate_buurtcode_systematiek(buurtkaart_path, buurtgegevens_path)
