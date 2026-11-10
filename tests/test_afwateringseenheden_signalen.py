"""Visible crossing selection, original geometries and human review persistence."""

import geopandas as gpd
import pyogrio
import pytest
from shapely.geometry import LineString, MultiLineString, MultiPolygon, box

from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen.afwateringseenheden import signalen, write_duiker_signaalkaart
from waterlagen.settings import settings


def make_run(path, geometries, *, polygons=None, official=True, treatment="aanvoer"):
    path.mkdir(parents=True, exist_ok=True)
    areas = gpd.GeoDataFrame(
        {"segment_key": ["A", "B"]},
        geometry=polygons or [box(0, 0, 10, 10), box(10, 0, 20, 10)],
        crs=settings.crs,
    )
    areas.to_file(path / "afwateringseenheden.gpkg", layer="afvoergebiedaanvoergebied")
    culverts = gpd.GeoDataFrame(
        {
            "bron": ["hydamo"] * len(geometries),
            "bron_id": [f"culvert-{i}" for i in range(len(geometries))],
            "nen3610id": [
                f"NL.WBHCODE.38.duiker.{i}" if official else None
                for i in range(len(geometries))
            ],
            "bronbestand": "original.gpkg",
            "bronlaag": "duikersifonhevel",
            "bron_fid": range(len(geometries)),
            "bronversie": "version-one",
            "behandeling": treatment,
            "reden": "minder dan twee aansluitingen",
        },
        geometry=geometries,
        crs=settings.crs,
    )
    culverts.to_file(path / "controle.gpkg", layer="duikers_waternet")
    return culverts


def read(path, layer=signalen.LINE_LAYER):
    return gpd.read_file(path, layer=layer)


def assert_simple_layers(path, *, polygon=False, archive=False):
    layers = dict(pyogrio.list_layers(path))
    review_layer = signalen.POLYGON_LAYER if polygon else signalen.LINE_LAYER
    expected = {review_layer}
    if archive:
        expected.add(signalen.ARCHIVE_TABLE)
        assert layers[signalen.ARCHIVE_TABLE] is None
    assert set(layers) == expected
    assert layers[review_layer] is not None
    assert list(read(path, review_layer).columns) == signalen.REVIEW_COLUMNS


def assess(path, layer=signalen.LINE_LAYER):
    features = read(path, layer)
    features.loc[
        0, ["bestaan", "ligging", "opmerking", "beoordelaar", "datum_beoordeling"]
    ] = [
        "bestaat",
        "correct",
        "Veldbezoek",
        "Waterschap",
        "2026-11-10",
    ]
    write_geopackage_layer_atomically(
        features, path, layer_name=layer, preserve_other_layers=True
    )


@pytest.mark.parametrize(
    ("geometry", "count"),
    [
        (LineString([(5, 5), (15, 5)]), 1),
        (LineString([(5, 5), (10, 5), (15, 5)]), 1),
        (LineString([(5, 3), (15, 3), (5, 7)]), 2),
        (LineString([(5, 3), (10, 5), (5, 7)]), 0),
        (LineString([(10, 2), (10, 8)]), 0),
        (LineString([(5, 2), (10, 2), (10, 8), (15, 8)]), 0),
        (LineString([(-5, 5), (5, 5)]), 0),
        (MultiLineString([[(2, 2), (8, 2)], [(12, 2), (18, 2)]]), 0),
        (MultiLineString([[(5, 5), (10, 5)], [(10, 5), (15, 5)]]), 1),
    ],
)
def test_real_crossings_only(tmp_path, geometry, count):
    make_run(tmp_path, [geometry])
    target = write_duiker_signaalkaart(tmp_path)
    assert_simple_layers(target)
    signals = read(target)
    assert len(signals) == bool(count)
    if count:
        assert signals.geometry.iloc[0].equals(geometry)
        areas = read(tmp_path / "afwateringseenheden.gpkg", "afvoergebiedaanvoergebied")
        assert len(signalen._crossings(geometry, areas)) == count
        assert signals.ingebrand.iloc[0] == "onbekend"
        assert signals.id.iloc[0] == "NL.WBHCODE.38.duiker.0"


def test_gaps_and_disconnected_polygons_are_not_crossings(tmp_path):
    make_run(
        tmp_path,
        [LineString([(5, 5), (15, 5)])],
        polygons=[box(0, 0, 9, 10), box(11, 0, 20, 10)],
    )
    target = write_duiker_signaalkaart(tmp_path)
    assert read(target).empty
    make_run(tmp_path, [MultiPolygon([box(2, 2, 8, 8), box(12, 2, 18, 8)])])
    assert signalen.POLYGON_LAYER not in dict(
        pyogrio.list_layers(write_duiker_signaalkaart(tmp_path))
    )


def test_polygon_kept_as_polygon_and_reviewed_once(tmp_path):
    original = box(8, 2, 12, 8)
    make_run(tmp_path, [original, box(2, 2, 10, 8)])
    target = write_duiker_signaalkaart(tmp_path)
    assert signalen.LINE_LAYER not in dict(pyogrio.list_layers(target))
    signals = read(target, signalen.POLYGON_LAYER)
    assert len(signals) == 1
    assert signals.geometry.iloc[0].equals(original)
    assert_simple_layers(target, polygon=True)
    assess(target, signalen.POLYGON_LAYER)
    write_duiker_signaalkaart(tmp_path)
    assert read(target, signalen.POLYGON_LAYER).bestaan.iloc[0] == "bestaat"


def test_unburned_duiker_is_included_with_reason(tmp_path):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])], treatment="primair_primair")
    signals = read(write_duiker_signaalkaart(tmp_path))
    assert signals.ingebrand.iloc[0] == "nee"
    assert signals.reden_niet_ingebrand.iloc[0] == "uitsluitend primaire aansluitingen"


def test_existing_empty_layers_removed_and_review_fields_start_blank(tmp_path):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    target = write_duiker_signaalkaart(tmp_path)
    signals = read(target)
    assert signals[list(signalen.REVIEW_DEFAULTS)].fillna("").eq("").all().all()
    assert signals.id.tolist() == ["NL.WBHCODE.38.duiker.0"]
    signals.iloc[:0].to_file(target, layer=signalen.POLYGON_LAYER)
    signalen._write_archive(
        signalen._frame(
            [], [*signalen.SIGNAL_COLUMNS, "archiefreden", "gearchiveerd_op"]
        ),
        target,
    )
    assess(target)
    write_duiker_signaalkaart(tmp_path)
    assert_simple_layers(target)
    assert read(target).bestaan.tolist() == ["bestaat"]


def test_disappearing_polygon_review_is_archived_before_layer_removed(tmp_path):
    make_run(tmp_path, [box(8, 2, 12, 8)])
    target = write_duiker_signaalkaart(tmp_path)
    assess(target, signalen.POLYGON_LAYER)
    make_run(tmp_path, [box(2, 2, 8, 8)])
    write_duiker_signaalkaart(tmp_path)
    assert_simple_layers(target, archive=True)
    assert read(target, signalen.ARCHIVE_TABLE).bestaan.tolist() == ["bestaat"]
    write_duiker_signaalkaart(tmp_path)
    assert read(target, signalen.ARCHIVE_TABLE).bestaan.tolist() == ["bestaat"]


def test_old_id_fields_migrate_with_current_and_archived_reviews(tmp_path):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    target = write_duiker_signaalkaart(tmp_path)
    assess(target)
    old = read(target).rename(columns={"id": "officiele_id"})
    old["nen3610id"] = old.officiele_id
    old.to_file(target, layer=signalen.LINE_LAYER)
    write_duiker_signaalkaart(tmp_path)
    assert_simple_layers(target)
    assert read(target).bestaan.tolist() == ["bestaat"]
    # A disappearing old-format row must also retain its ID in the archive.
    old.to_file(target, layer=signalen.LINE_LAYER)
    make_run(tmp_path, [LineString([(2, 2), (8, 2)])])
    write_duiker_signaalkaart(tmp_path)
    archive = read(target, signalen.ARCHIVE_TABLE)
    assert archive.id.tolist() == ["NL.WBHCODE.38.duiker.0"]
    pyogrio.write_dataframe(
        archive.rename(columns={"id": "officiele_id"}),
        target,
        layer=signalen.ARCHIVE_TABLE,
    )
    write_duiker_signaalkaart(tmp_path)
    archive = read(target, signalen.ARCHIVE_TABLE)
    assert archive.id.tolist() == ["NL.WBHCODE.38.duiker.0"]
    assert archive.bestaan.tolist() == ["bestaat"]


def test_reviews_follow_official_id_not_path_or_fid_and_archive_changes(tmp_path):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    target = write_duiker_signaalkaart(tmp_path)
    assess(target)
    controls = read(tmp_path / "controle.gpkg", "duikers_waternet")
    controls["bronbestand"] = "relocated.gpkg"
    controls["bron_fid"] = 42
    controls["bronversie"] = "new-version"
    controls.to_file(tmp_path / "controle.gpkg", layer="duikers_waternet")
    write_duiker_signaalkaart(tmp_path)
    assert read(target).bestaan.iloc[0] == "bestaat"
    assert read(target).datum_beoordeling.iloc[0] == "2026-11-10"
    controls.geometry = [LineString([(5, 6), (15, 6)])]
    controls.to_file(tmp_path / "controle.gpkg", layer="duikers_waternet")
    write_duiker_signaalkaart(tmp_path)
    assert read(target).bestaan.fillna("").iloc[0] == ""
    archive = read(target, signalen.ARCHIVE_TABLE)
    assert archive.bestaan.tolist() == ["bestaat"]
    assert archive.archiefreden.tolist() == ["geometrie gewijzigd"]
    write_duiker_signaalkaart(tmp_path)
    assert len(read(target, signalen.ARCHIVE_TABLE)) == 1


@pytest.mark.parametrize("change", ["disappear", "id", "source_version"])
def test_no_geometry_only_matching_and_disappeared_review_archived(tmp_path, change):
    make_run(
        tmp_path, [LineString([(5, 5), (15, 5)])], official=change != "source_version"
    )
    target = write_duiker_signaalkaart(tmp_path)
    assess(target)
    controls = read(tmp_path / "controle.gpkg", "duikers_waternet")
    if change == "disappear":
        controls.geometry = [LineString([(2, 2), (8, 2)])]
    elif change == "id":
        controls["nen3610id"] = "different-id"
    else:
        controls["bronversie"] = "new-version"
    controls.to_file(tmp_path / "controle.gpkg", layer="duikers_waternet")
    write_duiker_signaalkaart(tmp_path)
    current = read(target)
    assert current.empty or current.bestaan.fillna("").iloc[0] == ""
    assert read(target, signalen.ARCHIVE_TABLE).bestaan.tolist() == ["bestaat"]


def test_atomic_failure_keeps_reviews(tmp_path, monkeypatch):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    target = write_duiker_signaalkaart(tmp_path)
    assess(target)
    original = target.read_bytes()

    def fail(path):
        raise ValueError("failed validation")

    monkeypatch.setattr(signalen, "validate_geopackage", fail)
    with pytest.raises(ValueError, match="failed validation"):
        write_duiker_signaalkaart(tmp_path)
    assert target.read_bytes() == original


def test_mismatched_crs_rejected(tmp_path):
    controls = make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    controls.to_crs("EPSG:4326").to_file(
        tmp_path / "controle.gpkg", layer="duikers_waternet"
    )
    with pytest.raises(ValueError, match="CRS"):
        write_duiker_signaalkaart(tmp_path)


@pytest.mark.parametrize(
    ("origin", "fields", "expected"),
    [
        (
            "hydamo",
            {"nen3610id": "NL.WBHCODE.38.Duiker.123", "code": "D123"},
            "NL.WBHCODE.38.Duiker.123",
        ),
        (
            "bgt",
            {"identificatie.lokaalID": "bgt-object", "gml_id": "version-3"},
            "bgt-object",
        ),
        ("osm", {"osm_id": 123, "osm_type": "way"}, "way/123"),
    ],
)
def test_official_ids_survive_optional_preparation(tmp_path, origin, fields, expected):
    from test_afwateringseenheden_waternet import grid, sources

    from waterlagen.afwateringseenheden import (
        Brandlaag,
        BrandlagenConfig,
        read_brandlagen,
    )
    from waterlagen.afwateringseenheden.waternet import _classify_culverts

    geometry = LineString([(5, 5), (15, 5)])
    make_run(tmp_path, [geometry])
    source = tmp_path / "optional.gpkg"
    gpd.GeoDataFrame([fields], geometry=[geometry], crs=settings.crs).to_file(
        source, layer="duikers"
    )
    config = BrandlagenConfig(
        (Brandlaag(source, "duikers", rol="duiker", bron=origin),),
        brandwaarde=-10,
        prioriteit=1,
    )
    prepared = read_brandlagen(config)
    controls = _classify_culverts(sources(), prepared, grid())
    controls.to_file(tmp_path / "controle.gpkg", layer="duikers_waternet")
    result = read(write_duiker_signaalkaart(tmp_path))
    assert result.id.tolist() == [expected]
    for key, value in fields.items():
        assert controls[key].iloc[0] == str(value)


def test_duplicate_official_ids_keep_separate_source_registrations(tmp_path):
    controls = make_run(
        tmp_path, [LineString([(5, 4), (15, 4)]), LineString([(5, 6), (15, 6)])]
    )
    controls["nen3610id"] = "shared-official-id"
    controls.to_file(tmp_path / "controle.gpkg", layer="duikers_waternet")
    target = write_duiker_signaalkaart(tmp_path)
    signals = read(target)
    assert len(signals) == 2
    assert signals.duiker_key.nunique() == 2
    assess(target)
    write_duiker_signaalkaart(tmp_path)
    assert read(target).bestaan.fillna("").tolist() == ["bestaat", ""]


def test_reviews_can_be_carried_to_another_run_and_other_layers_survive(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    geometry = LineString([(5, 5), (15, 5)])
    make_run(first, [geometry])
    make_run(second, [geometry])
    previous = write_duiker_signaalkaart(first)
    assess(previous)
    target = write_duiker_signaalkaart(second, beoordelingen_path=previous)
    assert read(target).bestaan.tolist() == ["bestaat"]
    additional = gpd.GeoDataFrame(
        {"notitie": ["behouden"]}, geometry=[box(0, 0, 1, 1)], crs=settings.crs
    )
    additional.to_file(target, layer="eigen_notities")
    write_duiker_signaalkaart(second)
    assert read(target, "eigen_notities").notitie.tolist() == ["behouden"]


def test_old_archive_maps_migrate_without_losing_assessments_or_geometry(tmp_path):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    target = write_duiker_signaalkaart(tmp_path)
    assess(target)
    old_line = read(target)
    old_line["duiker_key"] = "historic-line"
    old_line["archiefreden"] = "signaal verdwenen"
    old_line["gearchiveerd_op"] = "2026-11-09"
    old_polygon = old_line.copy()
    old_polygon["duiker_key"] = "historic-polygon"
    old_polygon.geometry = [box(8, 2, 12, 8)]
    old_line.to_file(target, layer="beoordelingsarchief_lijnen")
    old_polygon.to_file(target, layer="beoordelingsarchief_vlakken")
    gpd.GeoDataFrame(
        geometry=[LineString([(10, 2), (10, 8)])], crs=settings.crs
    ).to_file(target, layer="duiker_grensdoorsnijdingen")
    gpd.GeoDataFrame(
        geometry=[old_line.geometry.iloc[0].centroid], crs=settings.crs
    ).to_file(target, layer="duiker_grenskruisingen")

    for _ in range(2):
        write_duiker_signaalkaart(tmp_path)
        assert_simple_layers(target, archive=True)
        assert read(target).bestaan.tolist() == ["bestaat"]
        archive = read(target, signalen.ARCHIVE_TABLE).set_index("duiker_key")
        assert len(archive) == 2
        assert archive.bestaan.tolist() == ["bestaat", "bestaat"]
        assert archive.datum_beoordeling.tolist() == ["2026-11-10", "2026-11-10"]
        assert (
            archive.loc["historic-line", "geometrie_wkb"]
            == old_line.geometry.iloc[0].wkb_hex
        )
        assert (
            archive.loc["historic-polygon", "geometrie_wkb"]
            == old_polygon.geometry.iloc[0].wkb_hex
        )
