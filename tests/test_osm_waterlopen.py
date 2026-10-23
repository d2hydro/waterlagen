"""Offline canal download, filtering, reuse and incomplete-response checks."""

from copy import deepcopy
from unittest.mock import Mock

import geopandas as gpd
import pytest

from waterlagen import _overpass
from waterlagen.datastore import DataStore
from waterlagen.osm_waterlopen import (
    download_osm_canals,
    download_osm_culverts,
    download_osm_waterlopen,
)

BOUNDS = (100000, 400000, 180000, 500000)


def way(identifier, **tags):
    return {
        "type": "way",
        "id": identifier,
        "tags": {"waterway": "canal", **tags},
        "geometry": [{"lon": 5.0, "lat": 52.0}, {"lon": 5.01, "lat": 52.0}],
    }


@pytest.fixture
def download(tmp_path, monkeypatch):
    store = DataStore(
        data_dir=tmp_path,
        source_data_dir=tmp_path / "source_data",
        processed_data_dir=tmp_path / "processed_data",
    )
    payload = {
        "osm3s": {"timestamp_osm_base": "2026-10-22T08:00:00Z"},
        "elements": [
            way(1, name="Kanaal"),
            way(2, tunnel="culvert"),
            way(3, tunnel="yes"),
            way(4, covered="yes"),
            way(5, location="underground"),
        ],
    }
    response = Mock()
    response.json.return_value = payload
    request = Mock(return_value=response)
    monkeypatch.setattr(_overpass.requests, "post", request)
    return store, payload, request


def test_download_open_canals_and_reuse(download):
    store, _, request = download
    path = download_osm_canals(BOUNDS, data_store=store)
    assert path == store.source_data_dir / "osm" / "osm_canals.gpkg"
    lines = gpd.read_file(path, layer="osm_canals")
    assert lines.osm_id.tolist() == [1]
    assert lines.crs.to_epsg() == 28992
    assert lines.geometry.geom_type.tolist() == ["LineString"]
    assert lines.osm_peildatum_utc.iloc[0] == "2026-10-22T08:00:00Z"
    assert lines.licentie.iloc[0] == "ODbL"
    assert 'way["waterway"="canal"]' in request.call_args.kwargs["data"]["data"]
    request.reset_mock()
    assert download_osm_canals(BOUNDS, data_store=store) == path
    request.assert_not_called()
    with pytest.raises(ValueError, match="andere invoer"):
        download_osm_canals((100000, 400000, 190000, 500000), data_store=store)
    request.assert_not_called()


@pytest.mark.parametrize("failure", ["remark", "geometry", "timestamp", "duplicate"])
def test_bad_response_preserves_existing_download(download, failure):
    store, payload, _ = download
    path = download_osm_canals(BOUNDS, data_store=store)
    before = path.read_bytes()
    if failure == "remark":
        payload["remark"] = "runtime error: timeout"
    elif failure == "geometry":
        del payload["elements"][0]["geometry"]
    elif failure == "timestamp":
        del payload["osm3s"]["timestamp_osm_base"]
    else:
        payload["elements"].append(deepcopy(payload["elements"][0]))
    with pytest.raises(ValueError):
        download_osm_canals(BOUNDS, data_store=store, overwrite=True)
    assert path.read_bytes() == before


def test_empty_selection_is_a_valid_layer(download):
    store, payload, _ = download
    payload["elements"] = []
    path = download_osm_canals(BOUNDS, data_store=store)
    assert gpd.read_file(path, layer="osm_canals").empty
    assert download_osm_canals(BOUNDS, data_store=store) == path


def test_full_geometry_retained_and_outside_way_removed(download):
    store, payload, _ = download
    # One way crosses the selected box; another is entirely outside it.
    payload["elements"] = [way(1), way(2)]
    payload["elements"][0]["geometry"][1] = {"lon": 6.5, "lat": 52.0}
    payload["elements"][1]["geometry"] = [
        {"lon": 6.5, "lat": 52.0},
        {"lon": 6.6, "lat": 52.0},
    ]
    path = download_osm_canals(BOUNDS, data_store=store)
    lines = gpd.read_file(path, layer="osm_canals")
    assert lines.osm_id.tolist() == [1]
    assert lines.total_bounds[2] > BOUNDS[2]


@pytest.mark.parametrize(
    ("waterway", "layer"),
    [("ditch", "osm_ditches"), ("drain", "osm_drains"), ("stream", "osm_streams")],
)
def test_download_smaller_waterways(download, waterway, layer):
    store, payload, request = download
    for element in payload["elements"]:
        element["tags"]["waterway"] = waterway
    path = download_osm_waterlopen(BOUNDS, waterway=waterway, data_store=store)
    assert path == store.source_data_dir / "osm" / f"{layer}.gpkg"
    lines = gpd.read_file(path, layer=layer)
    assert lines.osm_id.tolist() == [1]
    assert lines.waterway.tolist() == [waterway]
    assert lines.crs.to_epsg() == 28992
    assert f'way["waterway"="{waterway}"]' in request.call_args.kwargs["data"]["data"]
    request.reset_mock()
    assert download_osm_waterlopen(BOUNDS, waterway=waterway, data_store=store) == path
    request.assert_not_called()


def test_unknown_waterway_rejected_before_download(download):
    store, _, request = download
    with pytest.raises(ValueError, match="waterway moet"):
        download_osm_waterlopen(BOUNDS, waterway="river", data_store=store)
    request.assert_not_called()


def test_mismatched_waterway_preserves_existing_download(download):
    store, _, _ = download
    path = download_osm_canals(BOUNDS, data_store=store)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="OSM-waterloop"):
        download_osm_waterlopen(
            BOUNDS, path, waterway="ditch", data_store=store, overwrite=True
        )
    assert path.read_bytes() == before


@pytest.mark.parametrize("waterway", ["ditch", "stream", None])
def test_culverts_keep_underground_sections_and_actual_waterway(download, waterway):
    store, payload, request = download
    payload["elements"] = [
        way(
            7,
            waterway=waterway,
            tunnel="culvert",
            covered="yes",
            location="underground",
        )
    ]
    path = download_osm_culverts(BOUNDS, data_store=store)
    assert path.name == "osm_culverts.gpkg"
    lines = gpd.read_file(path, layer="osm_culvert")
    assert lines.osm_id.tolist() == [7]
    assert lines.waterway.iloc[0] == waterway
    assert 'way["tunnel"="culvert"]' in request.call_args.kwargs["data"]["data"]
    request.reset_mock()
    assert download_osm_culverts(BOUNDS, data_store=store) == path
    request.assert_not_called()
    payload["elements"][0]["tags"]["tunnel"] = "yes"
    before = path.read_bytes()
    with pytest.raises(ValueError, match="OSM-waterloop"):
        download_osm_culverts(BOUNDS, data_store=store, overwrite=True)
    assert path.read_bytes() == before


def test_empty_culvert_selection(download):
    store, payload, _ = download
    payload["elements"] = []
    path = download_osm_culverts(BOUNDS, data_store=store)
    assert gpd.read_file(path, layer="osm_culvert").empty
