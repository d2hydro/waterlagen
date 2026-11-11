"""BGT-only signal selection, existing connections and minimal output schema."""

from functools import partial
import shutil

import geopandas as gpd
import pandas as pd
import pyogrio
import pytest
from shapely.geometry import LineString, MultiLineString, MultiPolygon, box

from waterlagen.afwateringseenheden import signalen, write_duiker_signaalkaart
from waterlagen.settings import settings


@pytest.fixture(scope="module")
def base_run(tmp_path_factory):
    """Write immutable base layers once; each run receives independent copies."""
    path = tmp_path_factory.mktemp("signal_base")
    gpd.GeoDataFrame(
        {"segment_key": ["A", "B"]},
        geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10)],
        crs=settings.crs,
    ).to_file(path / "afwateringseenheden.gpkg", layer="afvoergebiedaanvoergebied")
    empty = gpd.GeoDataFrame(geometry=[], crs=settings.crs)
    empty.to_file(path / "brandlagen.gpkg", layer="hydamo_primair")
    empty.to_file(path / "brandlagen.gpkg", layer="hydamo_secundair")
    empty.to_file(path / "watersysteem.gpkg", layer="hydroobject_secundair")
    gpd.GeoDataFrame(
        {"segment_id": [], "segment_key": []}, geometry=[], crs=settings.crs
    ).to_file(path / "watersysteem.gpkg", layer="hydroobject_segment")
    gpd.GeoDataFrame(
        {"van_segment": [], "naar_segment": []}, geometry=[], crs=settings.crs
    ).to_file(path / "watersysteem.gpkg", layer="hydroobject_verbinding")
    return path


@pytest.fixture
def make_run(base_run):
    return partial(_make_run, base_run=base_run)


def _make_run(path, geometries, *, base_run, polygons=None):
    path.mkdir(parents=True, exist_ok=True)
    for filename in (
        "afwateringseenheden.gpkg",
        "brandlagen.gpkg",
        "watersysteem.gpkg",
    ):
        shutil.copyfile(base_run / filename, path / filename)
    if polygons is not None:
        gpd.GeoDataFrame(
            {"segment_key": ["A", "B"]}, geometry=polygons, crs=settings.crs
        ).to_file(path / "afwateringseenheden.gpkg", layer="afvoergebiedaanvoergebied")
    culverts = gpd.GeoDataFrame(
        {
            "gml_id": [f"gml-duiker-{i}" for i in range(len(geometries))],
            "identificatie.lokaalID": [
                f"G0001.duiker.{i}" for i in range(len(geometries))
            ],
        },
        geometry=geometries,
        crs=settings.crs,
    )
    source = path / signalen.BGT_SOURCE
    source.parent.mkdir(parents=True, exist_ok=True)
    culverts.to_file(source, layer="bgt_duiker")
    return culverts


def read(path, layer=signalen.LINE_LAYER):
    return gpd.read_file(path, layer=layer)


def assert_simple_layers(path, *, polygon=False):
    layer = signalen.POLYGON_LAYER if polygon else signalen.LINE_LAYER
    assert set(dict(pyogrio.list_layers(path))) == {layer}
    assert list(read(path, layer).columns) == ["id", "bronhouder", "geometry"]


@pytest.mark.parametrize("polygon", [False, True])
@pytest.mark.parametrize("holder", ["W0654", None])
def test_source_holder_is_preserved_without_guessing_from_id(
    make_run, tmp_path, polygon, holder
):
    geometry = box(5, 4, 15, 6) if polygon else LineString([(5, 5), (15, 5)])
    source = make_run(tmp_path, [geometry])
    source["bronhouder"] = pd.Series([holder], dtype="string")
    source.to_file(tmp_path / signalen.BGT_SOURCE, layer="bgt_duiker")
    output = write_duiker_signaalkaart(tmp_path)
    layer = signalen.POLYGON_LAYER if polygon else signalen.LINE_LAYER
    result = read(output, layer)
    assert result.id.iloc[0] == "gml-duiker-0"
    if holder is None:
        assert pd.isna(result.bronhouder.iloc[0])
    else:
        assert result.bronhouder.iloc[0] == holder


def test_missing_source_holder_column_remains_unknown(make_run, tmp_path):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    assert read(write_duiker_signaalkaart(tmp_path)).bronhouder.isna().all()


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_gml_id_is_rejected(make_run, tmp_path, value):
    source = make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    source["gml_id"] = pd.Series([value], dtype="string")
    source.to_file(tmp_path / signalen.BGT_SOURCE, layer="bgt_duiker")
    with pytest.raises(ValueError, match="lege gml_id"):
        write_duiker_signaalkaart(tmp_path)


def test_missing_gml_id_is_not_replaced_by_local_id(make_run, tmp_path):
    source = make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    source.drop(columns="gml_id").to_file(
        tmp_path / signalen.BGT_SOURCE, layer="bgt_duiker"
    )
    with pytest.raises(ValueError, match="gml_id ontbreekt"):
        write_duiker_signaalkaart(tmp_path)


@pytest.mark.parametrize(
    ("geometry", "count"),
    [
        (LineString([(5, 5), (15, 5)]), 1),
        (LineString([(5, 5), (10, 5), (15, 5)]), 1),
        (LineString([(5, 3), (15, 3), (5, 7)]), 0),
        (LineString([(5, 3), (10, 5), (5, 7)]), 0),
        (LineString([(10, 2), (10, 8)]), 0),
        (LineString([(5, 2), (10, 2), (10, 8), (15, 8)]), 0),
        (LineString([(-5, 5), (5, 5)]), 0),
        (MultiLineString([[(2, 2), (8, 2)], [(12, 2), (18, 2)]]), 0),
        (MultiLineString([[(5, 5), (10, 5)], [(10, 5), (15, 5)]]), 1),
        (MultiLineString([[(5, 5), (15, 5)], [(3, 3), (4, 3)]]), 0),
        (LineString([(10, 5), (15, 5)]), 0),
    ],
)
def test_real_crossings_only(make_run, tmp_path, geometry, count):
    make_run(tmp_path, [geometry])
    target = write_duiker_signaalkaart(tmp_path)
    assert_simple_layers(target)
    signals = read(target)
    assert len(signals) == bool(count)
    if count:
        assert signals.geometry.iloc[0].equals(geometry)
        assert signals.id.iloc[0] == "gml-duiker-0"


def test_gaps_and_disconnected_polygons_are_not_crossings(make_run, tmp_path):
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


def test_mismatched_crs_rejected(make_run, tmp_path):
    controls = make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    controls.to_crs("EPSG:4326").to_file(
        tmp_path / signalen.BGT_SOURCE, layer="bgt_duiker"
    )
    with pytest.raises(ValueError, match="CRS"):
        write_duiker_signaalkaart(tmp_path)


def test_hydamo_and_osm_burn_inputs_are_never_signal_sources(make_run, tmp_path):
    make_run(tmp_path, [box(8, 2, 12, 8)])
    controls = gpd.GeoDataFrame(
        {
            "bron": ["hydamo", "osm"],
            "bron_id": ["hydamo-1", "osm-1"],
            "behandeling": "aanvoer",
            "reden": "",
        },
        geometry=[LineString([(5, 4), (15, 4)]), LineString([(5, 6), (15, 6)])],
        crs=settings.crs,
    )
    controls.to_file(tmp_path / "controle.gpkg", layer="duikers_waternet")
    controls.to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_duikers")
    target = write_duiker_signaalkaart(tmp_path)
    assert_simple_layers(target, polygon=True)
    result = read(target, signalen.POLYGON_LAYER)
    assert result.id.tolist() == ["gml-duiker-0"]


def test_missing_bgt_source_fails_instead_of_falling_back_to_controls(
    make_run, tmp_path
):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    (tmp_path / signalen.BGT_SOURCE).unlink()
    with pytest.raises(FileNotFoundError, match="BGT-duikerbron"):
        write_duiker_signaalkaart(tmp_path)


@pytest.mark.parametrize(
    ("filename", "layer"),
    [
        ("brandlagen.gpkg", "hydamo_primair"),
        ("watersysteem.gpkg", "hydroobject_secundair"),
        ("brandlagen.gpkg", "hydamo_tertiair"),
    ],
)
@pytest.mark.parametrize("polygon", [False, True])
def test_non_primary_or_unverified_connections_keep_crossing_signals(
    make_run, tmp_path, filename, layer, polygon
):
    # Distances to y=0: inside, exactly 2 m, just outside; last does not cross.
    geometries = [
        box(5, y, 15, y + 0.5) if polygon else LineString([(5, y), (15, y)])
        for y in (1.0, 2.0, 2.01)
    ]
    geometries.append(box(3, 5, 7, 6) if polygon else LineString([(3, 5), (7, 5)]))
    make_run(tmp_path, geometries)
    gpd.GeoDataFrame(
        geometry=[LineString([(0, 0), (20, 0)])], crs=settings.crs
    ).to_file(tmp_path / filename, layer=layer)
    target = write_duiker_signaalkaart(tmp_path)
    signals = read(target, signalen.POLYGON_LAYER if polygon else signalen.LINE_LAYER)
    expected_positions = [0, 1, 2]
    if layer == "hydroobject_secundair":
        expected_positions = [1, 2] if polygon else [2]
    assert signals.id.tolist() == [f"gml-duiker-{i}" for i in expected_positions]
    assert all(
        geometry.equals(geometries[i])
        for geometry, i in zip(signals.geometry, expected_positions)
    )


def test_hydamo_culverts_and_optional_waterlines_do_not_exclude_bgt(make_run, tmp_path):
    geometry = LineString([(5, 5), (15, 5)])
    make_run(tmp_path, [geometry])
    for layer in ("hydamo_duikers", "osm_canals"):
        gpd.GeoDataFrame(geometry=[geometry], crs=settings.crs).to_file(
            tmp_path / "brandlagen.gpkg", layer=layer
        )
    assert read(write_duiker_signaalkaart(tmp_path)).id.tolist() == ["gml-duiker-0"]


def test_missing_waterlines_fails_instead_of_skipping_connection_check(
    make_run, tmp_path
):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    (tmp_path / "brandlagen.gpkg").unlink()
    with pytest.raises(FileNotFoundError, match="waterlopen"):
        write_duiker_signaalkaart(tmp_path)


def test_original_primary_line_excludes_bgt_at_gap_in_burn_pieces(make_run, tmp_path):
    make_run(tmp_path, [LineString([(8, 5), (12, 5)])])
    gpd.GeoDataFrame(
        {"bron_id": ["primary-source"]},
        geometry=[LineString([(0, 5), (20, 5)])],
        crs=settings.crs,
    ).to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    # The culvert section is missing from the primary burn pieces.
    gpd.GeoDataFrame(
        geometry=[LineString([(0, 5), (4, 5)]), LineString([(16, 5), (20, 5)])],
        crs=settings.crs,
    ).to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_primair")
    gpd.GeoDataFrame(
        {"segment_id": [1], "segment_key": ["A"], "bron_id": ["primary-source"]},
        geometry=[LineString([(0, 5), (4, 5)])],
        crs=settings.crs,
    ).to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_segment")
    assert read(write_duiker_signaalkaart(tmp_path)).empty


@pytest.mark.parametrize("polygon", [False, True])
@pytest.mark.parametrize("endpoint_only", [False, True])
def test_unconnected_secondary_waterlines_do_not_exclude_culverts(
    make_run, tmp_path, polygon, endpoint_only
):
    geometry = box(5, 4, 15, 6) if polygon else LineString([(5, 5), (15, 5)])
    make_run(tmp_path, [geometry])
    waterlines = [LineString([(0, 5), (20, 5)])]
    if endpoint_only:
        waterlines = [
            LineString([(3.1, 0), (3.1, 10)]),
            LineString([(16.9, 0), (16.9, 10)]),
        ]
    unconnected = gpd.GeoDataFrame(geometry=waterlines, crs=settings.crs)
    unconnected.to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_secundair")
    unconnected.to_file(
        tmp_path / "watersysteem.gpkg", layer="hydroobject_secundair_niet_verbonden"
    )
    target = write_duiker_signaalkaart(tmp_path)
    signals = read(target, signalen.POLYGON_LAYER if polygon else signalen.LINE_LAYER)
    assert signals.id.tolist() == ["gml-duiker-0"]


def test_missing_primary_topology_fails(
    make_run,
    tmp_path,
):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    (tmp_path / "watersysteem.gpkg").unlink()
    with pytest.raises(FileNotFoundError, match="waterlopen"):
        write_duiker_signaalkaart(tmp_path)


@pytest.mark.parametrize("polygon", [False, True])
def test_crossing_hydamo_at_one_point_does_not_exclude_whole_culvert(
    make_run, tmp_path, polygon
):
    geometry = box(1, 4, 19, 6) if polygon else LineString([(1, 5), (19, 5)])
    make_run(tmp_path, [geometry])
    gpd.GeoDataFrame(
        geometry=[LineString([(8, 0), (8, 10)])], crs=settings.crs
    ).to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    target = write_duiker_signaalkaart(tmp_path)
    signals = read(target, signalen.POLYGON_LAYER if polygon else signalen.LINE_LAYER)
    assert signals.id.tolist() == ["gml-duiker-0"]
    assert signals.geometry.iloc[0].equals(geometry)


@pytest.mark.parametrize("water_x", [3.1, 16.9])
@pytest.mark.parametrize("reverse", [False, True])
def test_near_endpoint_alone_does_not_exclude_line(
    make_run, tmp_path, water_x, reverse
):
    coordinates = [(5, 5), (15, 5)]
    if reverse:
        coordinates.reverse()
    make_run(tmp_path, [LineString(coordinates)])
    gpd.GeoDataFrame(
        geometry=[LineString([(water_x, 0), (water_x, 10)])], crs=settings.crs
    ).to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    assert read(write_duiker_signaalkaart(tmp_path)).id.tolist() == ["gml-duiker-0"]


@pytest.mark.parametrize(
    ("end_distance", "expected_count"), [(1.9, 1), (2.0, 1), (2.01, 1)]
)
@pytest.mark.parametrize("reverse", [False, True])
def test_separate_waterlines_at_both_endpoints_do_not_exclude(
    make_run, tmp_path, end_distance, expected_count, reverse
):
    coordinates = [(5, 5), (15, 5)]
    if reverse:
        coordinates.reverse()
    make_run(tmp_path, [LineString(coordinates)])
    # Nearby waterlines are separate and do not form one connection.
    gpd.GeoDataFrame(
        geometry=[
            LineString([(3.1, 0), (3.1, 10)]),
            LineString([(15 + end_distance, 0), (15 + end_distance, 10)]),
        ],
        crs=settings.crs,
    ).to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    assert len(read(write_duiker_signaalkaart(tmp_path))) == expected_count


@pytest.mark.parametrize(
    ("start_layer", "end_layer"),
    [
        ("hydroobject_secundair", "hydroobject_secundair"),
        ("hydamo_tertiair", "hydamo_tertiair"),
        ("hydamo_primair", "hydroobject_secundair"),
        ("hydroobject_secundair", "hydamo_primair"),
        ("hydamo_primair", "hydamo_tertiair"),
    ],
)
def test_separate_waterlines_do_not_form_an_existing_route(
    make_run, tmp_path, start_layer, end_layer
):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    layers = {}
    for layer, x in ((start_layer, 3.1), (end_layer, 16.9)):
        layers.setdefault(layer, []).append(LineString([(x, 0), (x, 10)]))
    for layer, geometries in layers.items():
        filename = (
            "watersysteem.gpkg"
            if layer == "hydroobject_secundair"
            else "brandlagen.gpkg"
        )
        gpd.GeoDataFrame(geometry=geometries, crs=settings.crs).to_file(
            tmp_path / filename, layer=layer
        )
    assert read(write_duiker_signaalkaart(tmp_path)).id.tolist() == ["gml-duiker-0"]


def test_connected_multiline_kept_when_endpoint_waterlines_are_separate(
    make_run, tmp_path
):
    geometry = MultiLineString([[(5, 5), (10, 5)], [(15, 5), (10, 5)]])
    make_run(tmp_path, [geometry])
    gpd.GeoDataFrame(
        geometry=[
            LineString([(3.1, 0), (3.1, 10)]),
            LineString([(16.9, 0), (16.9, 10)]),
        ],
        crs=settings.crs,
    ).to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    assert read(write_duiker_signaalkaart(tmp_path)).id.tolist() == ["gml-duiker-0"]


def test_connected_multiline_preserves_geometry_after_connection_check(
    make_run, tmp_path
):
    geometry = MultiLineString([[(1, 5), (10, 5)], [(19, 5), (10, 5)]])
    make_run(tmp_path, [geometry])
    gpd.GeoDataFrame(
        geometry=[LineString([(10, 0), (10, 10)])], crs=settings.crs
    ).to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    signals = read(write_duiker_signaalkaart(tmp_path))
    assert signals.id.tolist() == ["gml-duiker-0"]
    assert signals.geometry.iloc[0].equals(geometry)


@pytest.mark.parametrize("polygon", [False, True])
@pytest.mark.parametrize("percent", [49.99, 50.0, 100.0])
def test_unverified_primary_coverage_does_not_exclude_culvert(
    make_run, tmp_path, polygon, percent
):
    geometry = box(0, 4, 100, 6) if polygon else LineString([(0, 5), (100, 5)])
    make_run(
        tmp_path,
        [geometry],
        polygons=[box(-10, 0, 50, 10), box(50, 0, 110, 10)],
    )
    # Overlapping buffers form one zone from x=0 through x=percent.
    positions = [*range(0, int(percent) - 2, 4), percent - 2]
    gpd.GeoDataFrame(
        geometry=[LineString([(x, -10), (x, 20)]) for x in positions],
        crs=settings.crs,
    ).to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    target = write_duiker_signaalkaart(tmp_path)
    signals = read(target, signalen.POLYGON_LAYER if polygon else signalen.LINE_LAYER)
    assert signals.id.tolist() == ["gml-duiker-0"]
    assert signals.geometry.iloc[0].equals(geometry)


def test_existing_connection_across_multiple_original_waterlines_excludes(
    make_run, tmp_path
):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    gpd.GeoDataFrame(
        {"bron_id": ["first", "second"]},
        geometry=[LineString([(0, 5), (10, 5)]), LineString([(10, 5), (20, 5)])],
        crs=settings.crs,
    ).to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    gpd.GeoDataFrame(
        {
            "segment_id": [1, 2],
            "segment_key": ["A", "B"],
            "bron_id": ["first", "second"],
        },
        geometry=[LineString([(0, 5), (10, 5)]), LineString([(10, 5), (20, 5)])],
        crs=settings.crs,
    ).to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_segment")
    assert read(write_duiker_signaalkaart(tmp_path)).empty


def test_existing_run_can_use_explicit_bgt_source_without_burn_controls(
    make_run, tmp_path
):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    source = tmp_path / "bgt.gpkg"
    (tmp_path / signalen.BGT_SOURCE).replace(source)
    target = write_duiker_signaalkaart(tmp_path, bgt_duikers_path=source)
    signals = read(target)
    assert signals.id.tolist() == ["gml-duiker-0"]


def test_only_current_bgt_culverts_are_included(make_run, tmp_path):
    features = make_run(tmp_path, [LineString([(5, y), (15, y)]) for y in range(1, 6)])
    features["plus-type"] = ["duiker", "brug", "duiker", "duiker", "duiker"]
    features["bgt-status"] = ["bestaand", "bestaand", "plan", "bestaand", "bestaand"]
    features["eindRegistratie"] = [None, None, None, "2020-01-01", None]
    features["objectEindTijd"] = [None, None, None, None, "2020-01-01"]
    features.to_file(tmp_path / signalen.BGT_SOURCE, layer="bgt_duiker")
    assert read(write_duiker_signaalkaart(tmp_path)).id.tolist() == ["gml-duiker-0"]


def test_polygon_keeps_original_geometry_and_source_fields(make_run, tmp_path):
    original = box(8, 2, 12, 8)
    make_run(tmp_path, [original, box(2, 2, 10, 8)])
    target = write_duiker_signaalkaart(tmp_path)
    assert_simple_layers(target, polygon=True)
    signals = read(target, signalen.POLYGON_LAYER)
    assert signals.id.tolist() == ["gml-duiker-0"]
    assert signals.geometry.iloc[0].equals(original)


@pytest.mark.parametrize(
    "column", ["identificatie", "lokaalID", "identificatie.lokaalID"]
)
def test_gml_id_is_used_regardless_of_other_identifier_fields(
    make_run, tmp_path, column
):
    features = make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    features = features.rename(columns={"identificatie.lokaalID": column})
    features.to_file(tmp_path / signalen.BGT_SOURCE, layer="bgt_duiker")
    assert read(write_duiker_signaalkaart(tmp_path)).id.tolist() == ["gml-duiker-0"]


def test_regeneration_removes_old_fields_and_archive(make_run, tmp_path):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    target = write_duiker_signaalkaart(tmp_path)
    old = read(target)
    old["bestaan"] = "bestaat"
    old["ingebrand"] = "ja"
    old.to_file(target, layer=signalen.LINE_LAYER)
    old.to_file(target, layer="beoordelingsarchief_lijnen")
    old.iloc[:0].to_file(target, layer=signalen.POLYGON_LAYER)
    write_duiker_signaalkaart(tmp_path)
    assert_simple_layers(target)


def test_atomic_failure_keeps_previous_map(make_run, tmp_path, monkeypatch):
    make_run(tmp_path, [LineString([(5, 5), (15, 5)])])
    target = write_duiker_signaalkaart(tmp_path)
    original = target.read_bytes()

    def fail(path):
        raise ValueError("failed validation")

    monkeypatch.setattr(signalen, "validate_geopackage", fail)
    with pytest.raises(ValueError, match="failed validation"):
        write_duiker_signaalkaart(tmp_path)
    assert target.read_bytes() == original


def make_connection_run(make_run, path, *, reverse=False, width=100):
    coordinates = [(0, 5), (width, 5)]
    if reverse:
        coordinates.reverse()
    make_run(
        path,
        [LineString(coordinates)],
        polygons=[box(-10, 0, width / 2, 30), box(width / 2, 0, width + 10, 30)],
    )


def write_primary_target_route(path, *, connected):
    """Two drainage targets with an intermediate segment that has no own area."""
    targets = gpd.GeoDataFrame(
        {"segment_id": [1, 2, 3], "segment_key": ["A", "between", "B"]},
        geometry=[
            LineString([(0, 20), (49, 20)]),
            LineString([(49, 20), (51, 20)]),
            LineString([(51, 20), (100, 20)]),
        ],
        crs=settings.crs,
    )
    targets.to_file(path / "watersysteem.gpkg", layer="hydroobject_segment")
    if connected:
        gpd.GeoDataFrame(
            {"van_segment": [1, 2], "naar_segment": [2, 3]},
            geometry=gpd.points_from_xy([49, 51], [20, 20]),
            crs=settings.crs,
        ).to_file(path / "watersysteem.gpkg", layer="hydroobject_verbinding")


@pytest.mark.parametrize("reverse", [False, True])
def test_primary_target_alone_does_not_remove_distant_culvert(
    make_run, tmp_path, reverse
):
    make_connection_run(make_run, tmp_path, reverse=reverse)
    write_primary_target_route(tmp_path, connected=True)
    # A primary drainage target is not a physical primary attachment.
    assert len(read(write_duiker_signaalkaart(tmp_path))) == 1


@pytest.mark.parametrize(
    "end_distance, connected, used, excluded",
    [
        (1.8, True, True, True),
        (2.0, True, True, True),
        (2.01, True, True, False),
        (3.0, True, True, False),
        (1.8, False, True, False),
        (1.8, True, False, False),
    ],
)
def test_local_attachment_requires_distance_and_used_connected_route(
    make_run, tmp_path, end_distance, connected, used, excluded
):
    # The bent culvert has less than 50% buffer coverage: only the route can exclude it.
    make_run(
        tmp_path,
        [LineString([(5, 18), (50, 5), (95, 20 - end_distance)])],
        polygons=[box(0, 0, 50, 30), box(50, 0, 100, 30)],
    )
    write_primary_target_route(tmp_path, connected=connected)
    segments = read(tmp_path / "watersysteem.gpkg", "hydroobject_segment")
    segments["bron_id"] = segments.segment_key
    segments.to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_segment")
    primary = segments.loc[segments.segment_key.isin(["A", "B"])].copy()
    if not used:
        primary["bron_id"] = ["unused-first", "unused-last"]
    primary.to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    assert read(write_duiker_signaalkaart(tmp_path)).empty == excluded


def test_primary_targets_override_proximity_to_another_connection(make_run, tmp_path):
    make_connection_run(make_run, tmp_path)
    write_primary_target_route(tmp_path, connected=False)
    gpd.GeoDataFrame(
        geometry=[LineString([(0, 5), (100, 5)])], crs=settings.crs
    ).to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    # A nearby route is not evidence that the two actual drainage targets connect.
    assert len(read(write_duiker_signaalkaart(tmp_path))) == 1


@pytest.mark.parametrize(
    ("edges", "expected_count"),
    [
        ([(1, 2), (2, 3), (4, 2)], 0),  # A confluence on the existing route.
        ([(1, 2), (3, 2)], 0),  # A confluence connects both primary areas.
        ([(1, 2), (2, 3), (2, 4)], 0),  # A split still offers a route to the target.
        ([(3, 2), (2, 1), (4, 2)], 0),  # The route may run the opposite way.
        ([(1, 2), (2, 1)], 1),  # A cyclic route is not an established continuation.
        (
            [(1, 2), (2, 3), (3, 1)],
            0,
        ),  # A route reaches the target before returning through the cycle.
        ([(1, 2), (2, 3), (1, 2)], 0),  # Duplicate records are not a split.
    ],
)
def test_primary_route_distinguishes_confluence_split_and_common_receiver(
    make_run, tmp_path, edges, expected_count
):
    make_run(
        tmp_path,
        [LineString([(45, 5), (55, 5)])],
        polygons=[box(-10, 0, 50, 30), box(50, 0, 110, 30)],
    )
    write_primary_target_route(tmp_path, connected=False)
    targets = read(tmp_path / "watersysteem.gpkg", "hydroobject_segment")
    targets.loc[len(targets)] = [4, "side_branch", LineString([(50, 30), (50, 20)])]
    targets = targets.set_crs(settings.crs)
    targets.to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_segment")
    gpd.GeoDataFrame(
        {
            "van_segment": [source for source, _ in edges],
            "naar_segment": [target for _, target in edges],
        },
        geometry=gpd.points_from_xy([50] * len(edges), [20] * len(edges)),
        crs=settings.crs,
    ).to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_verbinding")
    targets["bron_id"] = targets.segment_key
    targets.to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_segment")
    gpd.GeoDataFrame(
        {"bron_id": ["A", "B"]},
        geometry=[
            LineString([(45, 5), (0, 20), (49, 20)]),
            LineString([(51, 20), (100, 20), (55, 5)]),
        ],
        crs=settings.crs,
    ).to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    assert len(read(write_duiker_signaalkaart(tmp_path))) == expected_count


@pytest.mark.parametrize("on_primary", [False, True])
@pytest.mark.parametrize("length", [20.0, 50.0, 5000.0])
@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_off_primary_route_keeps_signal_regardless_of_length(
    make_run, tmp_path, length, split, reverse, on_primary
):
    # Only actual primary attachments permit route-based exclusion.
    middle_length = length - 16
    height = 18 if on_primary else 17
    coordinates = [(-5, height), (middle_length / 2, 5), (middle_length + 5, height)]
    if reverse:
        coordinates.reverse()
    make_run(
        tmp_path,
        [LineString(coordinates)],
        polygons=[
            box(-2000, 0, middle_length / 2, 30),
            box(middle_length / 2, 0, middle_length + 2000, 30),
        ],
    )
    parts = [LineString([(0, 20), (middle_length, 20)])]
    if split:
        parts = [
            LineString([(0, 20), (middle_length / 2, 20)]),
            LineString([(middle_length / 2, 20), (middle_length, 20)]),
        ]
    geometries = [
        LineString([(-1000, 20), (0, 20)]),
        *parts,
        LineString([(middle_length, 20), (middle_length + 1000, 20)]),
        LineString([(middle_length + 1000, 20), (middle_length + 2000, 20)]),
    ]
    identifiers = list(range(1, len(geometries) + 1))
    keys = ["A", *[f"between-{i}" for i in range(len(parts))], "B", "beyond"]
    gpd.GeoDataFrame(
        {"segment_id": identifiers, "segment_key": keys, "bron_id": keys},
        geometry=geometries,
        crs=settings.crs,
    ).to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_segment")
    gpd.GeoDataFrame(
        {"van_segment": identifiers[:-1], "naar_segment": identifiers[1:]},
        geometry=gpd.points_from_xy(
            [g.coords[-1][0] for g in geometries[:-1]], [20] * (len(identifiers) - 1)
        ),
        crs=settings.crs,
    ).to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_verbinding")
    gpd.GeoDataFrame(
        {"bron_id": ["A", "B"]},
        geometry=[geometries[0], geometries[-2]],
        crs=settings.crs,
    ).to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    excluded = on_primary
    assert len(read(write_duiker_signaalkaart(tmp_path))) == (not excluded)


@pytest.mark.parametrize("on_primary", [False, True])
@pytest.mark.parametrize("multipart", [False, True])
@pytest.mark.parametrize(
    ("edges", "middle_length", "expected_count"),
    [
        ([(1, 2), (2, 3)], 2.0, 0),
        ([(1, 2)], 2.0, 1),  # A connection for two of three targets is insufficient.
        ([(1, 2), (3, 2)], 2.0, 0),  # Primary branches share an existing connection.
        ([(1, 2), (2, 3)], 20.0, 0),
        ([(1, 2), (2, 3)], 100.0, 0),  # Primary routes have no length limit.
    ],
)
def test_polygon_checks_all_overlapped_primary_targets(
    make_run,
    tmp_path,
    multipart,
    edges,
    middle_length,
    expected_count,
    on_primary,
    monkeypatch,
):
    geometry = box(48, 19, 50 + middle_length, 21)
    if multipart:
        geometry = MultiPolygon(
            [
                box(48, 18, 50 + middle_length, 19.5),
                box(48, 20.5, 50 + middle_length, 22),
            ]
        )
    make_run(tmp_path, [geometry])
    gpd.GeoDataFrame(
        {"segment_key": ["A", "between", "B"]},
        geometry=[
            box(-10, 0, 49, 30),
            box(49, 0, 49 + middle_length, 30),
            box(49 + middle_length, 0, 100 + middle_length, 30),
        ],
        crs=settings.crs,
    ).to_file(tmp_path / "afwateringseenheden.gpkg", layer="afvoergebiedaanvoergebied")
    write_primary_target_route(tmp_path, connected=False)
    targets = read(tmp_path / "watersysteem.gpkg", "hydroobject_segment")
    targets.loc[1, "geometry"] = LineString([(49, 20), (49 + middle_length, 20)])
    targets.loc[2, "geometry"] = LineString(
        [(49 + middle_length, 20), (100 + middle_length, 20)]
    )
    targets.to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_segment")
    gpd.GeoDataFrame(
        {"van_segment": [x for x, _ in edges], "naar_segment": [y for _, y in edges]},
        geometry=gpd.points_from_xy(
            [49 if x == 1 else 49 + middle_length for x, _ in edges], [20] * len(edges)
        ),
        crs=settings.crs,
    ).to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_verbinding")
    from waterlagen.afwateringseenheden import _signaalverbindingen

    targets["bron_id"] = targets.segment_key
    targets.to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_segment")
    if on_primary:
        targets.to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    # Isolate route validation from the independent 50% overlap exclusion.
    monkeypatch.setattr(
        _signaalverbindingen,
        "_overlaps_network_zone",
        lambda geometry, zones: False,
    )
    output = write_duiker_signaalkaart(tmp_path)
    excluded = signalen.POLYGON_LAYER not in dict(pyogrio.list_layers(output))
    assert excluded == (on_primary and expected_count == 0)
    if not excluded:
        assert read(output, signalen.POLYGON_LAYER).geometry.iloc[0].equals(geometry)


def test_polygon_boundary_touch_does_not_add_an_unconnected_target(
    make_run, tmp_path, monkeypatch
):
    make_run(tmp_path, [box(48, 19, 51, 21)])
    gpd.GeoDataFrame(
        {"segment_key": ["A", "between", "unconnected"]},
        geometry=[box(-10, 0, 49, 30), box(49, 0, 51, 30), box(51, 0, 110, 30)],
        crs=settings.crs,
    ).to_file(tmp_path / "afwateringseenheden.gpkg", layer="afvoergebiedaanvoergebied")
    write_primary_target_route(tmp_path, connected=True)
    from waterlagen.afwateringseenheden import _signaalverbindingen

    targets = read(tmp_path / "watersysteem.gpkg", "hydroobject_segment")
    targets["bron_id"] = targets.segment_key
    targets.to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_segment")
    targets.to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    monkeypatch.setattr(
        _signaalverbindingen,
        "_overlaps_network_zone",
        lambda geometry, zones: False,
    )
    output = write_duiker_signaalkaart(tmp_path)
    assert signalen.POLYGON_LAYER not in dict(pyogrio.list_layers(output))
    assert read(output).empty


@pytest.mark.parametrize("polygon", [False, True])
@pytest.mark.parametrize("percent", [33.0, 49.99, 50.0, 50.01, 100.0])
@pytest.mark.parametrize("used", [False, True])
def test_half_coverage_uses_original_primary_objects_with_final_areas(
    make_run, tmp_path, polygon, percent, used
):
    geometry = box(0, 4, 100, 6) if polygon else LineString([(0, 5), (100, 5)])
    make_run(
        tmp_path,
        [geometry],
        polygons=[box(-10, 0, 50, 10), box(50, 0, 110, 10)],
    )
    # The buffers overlap: the covered width is percent, never the sum of buffers.
    positions = [*range(0, int(percent) - 2, 3), percent - 2]
    waterlines = MultiLineString([[(x, -10), (x, 20)] for x in positions])
    gpd.GeoDataFrame(
        {"bron_id": ["primary-source"]}, geometry=[waterlines], crs=settings.crs
    ).to_file(tmp_path / "brandlagen.gpkg", layer="hydamo_primair")
    # Only this short piece has an area. The entire original source must be used.
    gpd.GeoDataFrame(
        {
            "segment_id": [1],
            "segment_key": ["A" if used else "unused"],
            "bron_id": ["primary-source"],
        },
        geometry=[LineString([(0, -10), (0, -9)])],
        crs=settings.crs,
    ).to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_segment")
    target = write_duiker_signaalkaart(tmp_path)
    excluded = used and percent >= 50
    if excluded:
        assert read(target).empty
        assert signalen.POLYGON_LAYER not in dict(pyogrio.list_layers(target))
    else:
        result = read(
            target, signalen.POLYGON_LAYER if polygon else signalen.LINE_LAYER
        )
        assert result.id.tolist() == ["gml-duiker-0"]
        assert result.geometry.iloc[0].equals(geometry)
