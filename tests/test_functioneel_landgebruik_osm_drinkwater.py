"""Small OSM responses exercise the download-to-BAG-source workflow."""

import json

import geopandas as gpd
import pyogrio
import pytest
from shapely.geometry import box

from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik.kassen_rwzi_drinkwater import (
    _match_site_buildings,
)
from waterlagen.functioneel_landgebruik.landgebruik_berekenen import (
    FunctioneelLandgebruikSources,
)
from waterlagen.functioneel_landgebruik.osm_drinkwater import (
    BUILDING_LAYER,
    DRINKWATER_LAYER,
    SITE_LAYER,
    download_osm_drinkwater,
)


def _way(identifier, *, name, building=False):
    tags = {"man_made": "water_works", "name": name, "operator": "Vitens"}
    if building:
        tags["building"] = "industrial"
    return {
        "type": "way",
        "id": identifier,
        "center": {"lon": 5.0 + identifier / 1000, "lat": 52.0},
        "tags": tags,
    }


def _detailed(element):
    result = element.copy()
    longitude = element["center"]["lon"]
    result["geometry"] = [
        {"lon": longitude, "lat": 52.0},
        {"lon": longitude + 0.001, "lat": 52.0},
        {"lon": longitude + 0.001, "lat": 52.001},
        {"lon": longitude, "lat": 52.001},
        {"lon": longitude, "lat": 52.0},
    ]
    return result


def test_osm_download_writes_terrain_and_review_layers(tmp_path):
    site = _way(1, name="Vitens productielocatie")
    building = _way(3, name="Vitens zuiveringsgebouw", building=True)
    ignored = _way(5, name="Industriewater Vitens")
    selection = {"elements": [site, building, ignored]}
    detail = {
        "elements": [_detailed(site), _detailed(building)],
        "osm3s": {"timestamp_osm_base": "2026-09-29T12:00:00Z"},
    }
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "selectie.json").write_text(json.dumps(selection), encoding="utf-8")
    (cache_dir / "geometrie.json").write_text(json.dumps(detail), encoding="utf-8")
    store = DataStore(
        data_dir=tmp_path,
        source_data_dir=tmp_path / "source",
        processed_data_dir=tmp_path / "processed",
    )
    output = download_osm_drinkwater(
        data_store=store, cache_dir=cache_dir, offline=True
    )
    assert output == store.source_data_dir / "osm" / "drinkwaterlocaties.gpkg"
    assert set(pyogrio.list_layers(output)[:, 0]) == {
        DRINKWATER_LAYER,
        SITE_LAYER,
        BUILDING_LAYER,
    }
    matching = gpd.read_file(output, layer=DRINKWATER_LAYER)
    assert len(matching) == 1
    assert matching.iloc[0].osm_ids == "way/1"
    assert matching.iloc[0].osm_peildatum_utc == "2026-09-29T12:00:00Z"
    assert matching.crs.to_epsg() == 28992
    assert len(gpd.read_file(output, layer=BUILDING_LAYER)) == 1
    assert (
        FunctioneelLandgebruikSources.from_datastore(store).drinking_water_gpkg
        == output
    )
    panden = gpd.GeoDataFrame(geometry=[matching.geometry.iloc[0]], crs=matching.crs)
    matches = _match_site_buildings(panden, matching)
    assert matches.iloc[0] == "way/1"

    # overwrite=False reuses the validated source without another API request.
    assert download_osm_drinkwater(data_store=store) == output


def test_osm_building_contours_can_be_included_explicitly(tmp_path, monkeypatch):
    building = _way(3, name="Vitens zuiveringsgebouw", building=True)
    responses = iter(
        [
            {"elements": [building]},
            {
                "elements": [_detailed(building)],
                "osm3s": {"timestamp_osm_base": "2026-09-29T12:00:00Z"},
            },
        ]
    )
    monkeypatch.setattr(
        "waterlagen.functioneel_landgebruik.osm_drinkwater._read_overpass",
        lambda *args, **kwargs: next(responses),
    )
    output = download_osm_drinkwater(
        target_path=tmp_path / "drinkwater.gpkg", include_buildings=True
    )
    assert len(gpd.read_file(output, layer=DRINKWATER_LAYER)) == 1
    assert len(gpd.read_file(output, layer=SITE_LAYER)) == 0


def test_missing_detail_does_not_replace_existing_output(tmp_path, monkeypatch):
    site = _way(1, name="Vitens productielocatie")
    responses = iter(
        [
            {"elements": [site]},
            {"elements": [], "osm3s": {"timestamp_osm_base": "2026-09-29T12:00:00Z"}},
        ]
    )
    monkeypatch.setattr(
        "waterlagen.functioneel_landgebruik.osm_drinkwater._read_overpass",
        lambda *args, **kwargs: next(responses),
    )
    output = tmp_path / "drinkwater.gpkg"
    output.write_bytes(b"bestaand")
    with pytest.raises(ValueError, match="mist locaties"):
        download_osm_drinkwater(target_path=output, overwrite=True)
    assert output.read_bytes() == b"bestaand"


def test_multipolygon_hole_stays_out_of_matching():
    from waterlagen.functioneel_landgebruik.osm_drinkwater import _polygon

    outer = [
        {"lon": x, "lat": y}
        for x, y in [(5, 52), (5.01, 52), (5.01, 52.01), (5, 52.01), (5, 52)]
    ]
    inner = [
        {"lon": x, "lat": y}
        for x, y in [
            (5.004, 52.004),
            (5.006, 52.004),
            (5.006, 52.006),
            (5.004, 52.006),
            (5.004, 52.004),
        ]
    ]
    relation = {
        "type": "relation",
        "id": 7,
        "tags": {"type": "multipolygon"},
        "members": [
            {"type": "way", "ref": 1, "role": "outer", "geometry": outer},
            {"type": "way", "ref": 2, "role": "inner", "geometry": inner},
        ],
    }
    geometry = _polygon(relation, {})
    assert geometry.covers(box(5.001, 52.001, 5.002, 52.002))
    assert not geometry.covers(box(5.0045, 52.0045, 5.0055, 52.0055))
