"""Reviewed OSM locations become traceable polygons for BAG matching."""

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
    REVIEWS_PATH,
    SITE_LAYER,
    _read_reviews,
    download_osm_drinkwater,
)


def _review(identifier, *, kind="terrein", judgement="drinkwaterzuivering"):
    return {
        "locatie_id": f"way/{identifier}",
        "naam": f"Vitens locatie {identifier}",
        "exploitant": "Vitens",
        "vlak_type": kind,
        "osm_ids": f"way/{identifier}",
        "oordeel": judgement,
        "controle_datum": "2026-09-29",
    }


def _way(identifier):
    longitude = 5 + identifier % 10 * 0.01
    return {
        "type": "way",
        "id": identifier,
        "geometry": [
            {"lon": longitude, "lat": 52.0},
            {"lon": longitude + 0.001, "lat": 52.0},
            {"lon": longitude + 0.001, "lat": 52.001},
            {"lon": longitude, "lat": 52.001},
            {"lon": longitude, "lat": 52.0},
        ],
    }


def _inputs(tmp_path, reviews, geometry_ids):
    reviews_path = tmp_path / "beoordelingen.json"
    reviews_path.write_text(json.dumps(reviews), encoding="utf-8")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "geometrie.json").write_text(
        json.dumps(
            {
                "elements": [_way(identifier) for identifier in geometry_ids],
                "osm3s": {"timestamp_osm_base": "2026-09-29T12:00:00Z"},
            }
        ),
        encoding="utf-8",
    )
    return reviews_path, cache_dir


def test_reviewed_sites_are_written_and_used_for_bag(tmp_path):
    reviews_path, cache_dir = _inputs(
        tmp_path,
        [
            _review(1),
            _review(3, kind="gebouw"),
            _review(5, judgement="deelzuivering"),
            _review(6, judgement="geen_zuivering"),
        ],
        [1, 3],
    )
    store = DataStore(
        data_dir=tmp_path,
        source_data_dir=tmp_path / "source",
        processed_data_dir=tmp_path / "processed",
    )
    output = download_osm_drinkwater(
        data_store=store, reviews_path=reviews_path, cache_dir=cache_dir, offline=True
    )
    assert output == store.source_data_dir / "osm" / "drinkwaterlocaties.gpkg"
    assert set(pyogrio.list_layers(output)[:, 0]) == {
        DRINKWATER_LAYER,
        SITE_LAYER,
        BUILDING_LAYER,
    }
    matching = gpd.read_file(output, layer=DRINKWATER_LAYER)
    assert list(matching.osm_ids) == ["way/1"]
    assert "bewijs" not in matching.columns
    assert "bronnen_functie" not in matching.columns
    assert "osm_urls" not in matching.columns
    assert "licentie_url" not in matching.columns
    assert matching.iloc[0].controle_datum == "2026-09-29"
    assert matching.iloc[0].osm_peildatum_utc == "2026-09-29T12:00:00Z"
    assert matching.crs.to_epsg() == 28992
    assert list(gpd.read_file(output, layer=BUILDING_LAYER).osm_ids) == ["way/3"]
    assert (
        FunctioneelLandgebruikSources.from_datastore(store).drinking_water_gpkg
        == output
    )
    panden = gpd.GeoDataFrame(geometry=[matching.geometry.iloc[0]], crs=matching.crs)
    assert _match_site_buildings(panden, matching).iloc[0] == "way/1"
    assert download_osm_drinkwater(data_store=store) == output


def test_building_contours_can_be_included_explicitly(tmp_path):
    reviews_path, cache_dir = _inputs(tmp_path, [_review(3, kind="gebouw")], [3])
    output = download_osm_drinkwater(
        target_path=tmp_path / "drinkwater.gpkg",
        reviews_path=reviews_path,
        cache_dir=cache_dir,
        offline=True,
        include_buildings=True,
    )
    assert list(gpd.read_file(output, layer=DRINKWATER_LAYER).osm_ids) == ["way/3"]
    assert gpd.read_file(output, layer=SITE_LAYER).empty


def test_user_exclusions_and_vechterweerd_are_kept(tmp_path):
    reviews_path, cache_dir = _inputs(
        tmp_path,
        [
            _review(1),
            _review(265176673, kind="gebouw"),
            _review(1487136894),
            _review(480242778, kind="gebouw"),
        ],
        [1, 480242778],
    )
    output = download_osm_drinkwater(
        target_path=tmp_path / "drinkwater.gpkg",
        reviews_path=reviews_path,
        cache_dir=cache_dir,
        offline=True,
    )
    assert list(gpd.read_file(output, layer=DRINKWATER_LAYER).osm_ids) == ["way/1"]
    assert list(gpd.read_file(output, layer=SITE_LAYER).osm_ids) == ["way/1"]
    assert list(gpd.read_file(output, layer=BUILDING_LAYER).osm_ids) == [
        "way/480242778"
    ]


def test_bundled_review_keeps_only_requested_locations():
    ids = {review.polygon_id for review in _read_reviews(REVIEWS_PATH)}
    assert len(ids) == 54
    assert "way/480242778" in ids
    assert "way/265176673" not in ids
    assert "way/1487136894" not in ids
    assert "way/1507213751" not in ids  # Geen zuivering: Aquaterp.


def test_missing_geometry_does_not_replace_existing_output(tmp_path):
    reviews_path, cache_dir = _inputs(tmp_path, [_review(1)], [])
    output = tmp_path / "drinkwater.gpkg"
    output.write_bytes(b"bestaand")
    with pytest.raises(ValueError, match="mist vlakken"):
        download_osm_drinkwater(
            target_path=output,
            reviews_path=reviews_path,
            cache_dir=cache_dir,
            offline=True,
            overwrite=True,
        )
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
