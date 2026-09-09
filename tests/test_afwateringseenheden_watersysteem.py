from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, MultiLineString, Point, box

from waterlagen.afwateringseenheden import (
    prepare_watersysteem,
    read_hydroobjecten,
    read_puntobjecten,
    split_connected_secondary_hydroobjecten,
    split_hydroobjecten_at_points,
    split_hydroobjecten_by_length,
    write_watersysteem,
)
from waterlagen.afwateringseenheden.lines import create_hydroobject_verbindingen
from waterlagen.afwateringseenheden import workflow
from waterlagen.settings import settings

CRS = settings.crs


def _write_hydamo(path: Path) -> Path:
    hydroobjecten = gpd.GeoDataFrame(
        {
            "code": ["h-primair", "h-secundair"],
            "globalid": ["hydro-primair", "hydro-secundair"],
            "naam": ["Primaire watergang", "Secundaire watergang"],
            "nen3610id": [
                "NL.WBHCODE.38.HydroObject.1",
                "NL.WBHCODE.59.HydroObject.2",
            ],
            "categorieoppwaterlichaam": ["primair", "secundair"],
        },
        geometry=[
            LineString([(0, 0, 3), (100, 0, 3)]),
            LineString([(0, 10, 4), (100, 10, 4)]),
        ],
        crs=CRS,
    )
    gemalen = gpd.GeoDataFrame(
        {
            "code": ["g-38", "g-59"],
            "globalid": ["gemaal-38", "gemaal-59"],
            "naam": ["Gemaal 38", "Gemaal 59"],
            "nen3610id": [
                "NL.WBHCODE.38.Gemaal.1",
                "NL.WBHCODE.59.Gemaal.2",
            ],
        },
        geometry=[Point(25, 1, 5), Point(25, 11, 5)],
        crs=CRS,
    )
    stuwen = gpd.GeoDataFrame(
        {
            "code": ["s-38", "s-59"],
            "globalid": ["stuw-38", "stuw-59"],
            "naam": ["Stuw 38", "Stuw 59"],
            "nen3610id": [
                "NL.WBHCODE.38.Stuw.1",
                "NL.WBHCODE.59.Stuw.2",
            ],
        },
        geometry=[Point(75, 0, 6), Point(75, 10, 6)],
        crs=CRS,
    )
    hydroobjecten.to_file(path, layer="hydroobject", driver="GPKG", index=False)
    gemalen.to_file(path, layer="gemaal", driver="GPKG", index=False, mode="a")
    stuwen.to_file(path, layer="stuw", driver="GPKG", index=False, mode="a")
    return path


@pytest.fixture
def hydamo_path(tmp_path) -> Path:
    return _write_hydamo(tmp_path / "hydamo.gpkg")


def _hydroobjecten() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "code": ["h-a", "h-b"],
            "globalid": ["hydro-a", "hydro-b"],
            "categorieoppwaterlichaam": ["primair", "primair"],
        },
        geometry=[
            LineString([(0, 0), (100, 0)]),
            LineString([(50, -50), (50, 50)]),
        ],
        crs=CRS,
    )


def _puntobjecten(points: list[Point]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "code": [f"s-{index}" for index in range(len(points))],
            "globalid": [f"stuw-{index}" for index in range(len(points))],
            "naam": ["Stuw" for _ in points],
            "objecttype": ["stuw" for _ in points],
            "waterbeheercode": ["38" for _ in points],
        },
        geometry=points,
        crs=CRS,
    )


def _segmenten(
    segment_ids: list[str],
    geometries: list[LineString],
) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "segment_id": segment_ids,
            "bron_id": [segment_id.split(":")[0] for segment_id in segment_ids],
        },
        geometry=geometries,
        crs=CRS,
    )


def _hydroobjecten_met_bron_ids(bron_ids: list[str]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "bron_id": bron_ids,
            "code": [f"code-{bron_id}" for bron_id in bron_ids],
        },
        geometry=[
            LineString([(index * 10, 0), (index * 10 + 5, 0)])
            for index in range(len(bron_ids))
        ],
        crs=CRS,
    )


def _bron_verbindingen(
    bron_id_pairs: list[tuple[str, str]],
) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "van_bron_id": [pair[0] for pair in bron_id_pairs],
            "naar_bron_id": [pair[1] for pair in bron_id_pairs],
        },
        geometry=[Point(index, 0) for index in range(len(bron_id_pairs))],
        crs=CRS,
    )


def test_read_hydroobjecten_applies_spatial_code_and_primary_filter(hydamo_path):
    result = read_hydroobjecten(
        hydamo_path,
        spatial_selection=box(-1, -2, 101, 2),
        waterbeheercodes=[38],
        attribute_filters={"categorieoppervlaktewater": ["primair"]},
    )

    assert result["code"].tolist() == ["h-primair"]
    assert result["bron_id"].tolist() == ["hydro-primair"]
    assert result["waterbeheercode"].tolist() == ["38"]
    assert result.crs.to_epsg() == 28992
    assert not result.geometry.has_z.any()


def test_read_hydroobjecten_requires_known_attribute_filter_column(hydamo_path):
    with pytest.raises(ValueError, match="onbekend"):
        read_hydroobjecten(
            hydamo_path,
            attribute_filters={"onbekend": ["waarde"]},
        )


def test_read_hydroobjecten_supports_multiple_waterbeheercodes(hydamo_path):
    result = read_hydroobjecten(hydamo_path, waterbeheercodes=["38", 59.0])

    assert sorted(result["waterbeheercode"]) == ["38", "59"]


def test_read_puntobjecten_combines_configured_layers_and_keeps_objecttype(hydamo_path):
    result = read_puntobjecten(
        hydamo_path,
        layers=("gemaal", "stuw"),
        spatial_selection=box(-1, -2, 101, 2),
        waterbeheercodes=["38", 59.0],
    )

    assert sorted(result["objecttype"]) == ["gemaal", "stuw"]
    assert sorted(result["waterbeheercode"]) == ["38", "38"]
    assert result["bron_id"].tolist() == ["gemaal-38", "stuw-38"]
    assert not result.geometry.has_z.any()


def test_read_hydroobjecten_explodes_multilines_and_warns(tmp_path, caplog):
    path = tmp_path / "multiline.gpkg"
    gpd.GeoDataFrame(
        {
            "globalid": ["multi"],
            "nen3610id": ["NL.WBHCODE.38.HydroObject.1"],
        },
        geometry=[MultiLineString([[(0, 0), (10, 0)], [(10, 0), (20, 0)]])],
        crs=CRS,
    ).to_file(path, layer="hydroobject", driver="GPKG", index=False)

    result = read_hydroobjecten(path)

    assert len(result) == 2
    assert "Exploding MultiLineString" in caplog.text


def test_prepare_watersysteem_accepts_geodataframes_and_transforms_crs():
    hydroobjecten = _hydroobjecten().to_crs("EPSG:4326")
    puntobjecten = _puntobjecten([Point(50, 0)]).to_crs("EPSG:4326")

    result = prepare_watersysteem(
        hydroobjecten,
        puntobjecten,
        tolerance=2,
        max_length=500,
    )

    assert result.hydroobject_segmenten.crs.to_epsg() == 28992
    assert result.hydroobject_verbinding.crs.to_epsg() == 28992


def test_point_within_tolerance_creates_directed_connection_tree_at_the_node():
    result = prepare_watersysteem(
        _hydroobjecten(),
        _puntobjecten([Point(50, 1)]),
        tolerance=2,
        max_length=500,
    )
    verbindingen = result.hydroobject_verbinding

    assert len(result.hydroobject_segmenten) == 4
    assert len(verbindingen) == 3
    assert {
        tuple(row)
        for row in verbindingen[["van_segment", "naar_segment"]].itertuples(
            index=False, name=None
        )
    } == {
        ("hydro-a:0001", "hydro-a:0002"),
        ("hydro-a:0001", "hydro-b:0002"),
        ("hydro-b:0001", "hydro-a:0002"),
    }
    assert set(verbindingen["objecttype"]) == {"stuw"}
    assert set(verbindingen["punt_bron_id"]) == {"stuw-0"}
    assert set(verbindingen["waterbeheercode"]) == {"38"}
    assert set(verbindingen.geom_type) == {"Point"}
    assert not verbindingen.geometry.has_z.any()


def test_prepare_watersysteem_drops_z_and_deduplicates_equal_connections():
    hydroobjecten = gpd.GeoDataFrame(
        {"globalid": ["hydro-a", "hydro-b"]},
        geometry=[
            LineString([(0, 0, 10), (100, 0, 10)]),
            LineString([(50, -50, 10), (50, 50, 10)]),
        ],
        crs=CRS,
    )
    puntobjecten = gpd.GeoDataFrame(
        {
            "globalid": ["stuw-a", "stuw-b"],
            "objecttype": ["stuw", "stuw"],
        },
        geometry=[Point(50, 0, 20), Point(50, 0, 30)],
        crs=CRS,
    )

    result = prepare_watersysteem(
        hydroobjecten,
        puntobjecten,
        tolerance=0,
        max_length=20,
    )

    assert not result.hydroobject_segmenten.geometry.has_z.any()
    assert set(result.hydroobject_verbinding.geom_type) == {"Point"}
    assert not result.hydroobject_verbinding.geometry.has_z.any()
    assert len(result.hydroobject_verbinding) == 11
    assert not result.hydroobject_verbinding.duplicated(
        ["van_segment", "naar_segment", "geometry"]
    ).any()


def test_length_segmentation_creates_connections_between_adjacent_segments():
    result = prepare_watersysteem(
        _hydroobjecten().iloc[[0]],
        _puntobjecten([]),
        max_length=30,
    )

    assert len(result.hydroobject_segmenten) == 4
    assert result.hydroobject_verbinding[
        ["van_segment", "naar_segment"]
    ].values.tolist() == [
        ["hydro-a:0001", "hydro-a:0002"],
        ["hydro-a:0002", "hydro-a:0003"],
        ["hydro-a:0003", "hydro-a:0004"],
    ]
    assert set(result.hydroobject_verbinding.geom_type) == {"Point"}


def test_one_incoming_and_two_outgoing_segments_create_two_directed_connections():
    segmenten = _segmenten(
        ["in:0001", "out-a:0001", "out-b:0001"],
        [
            LineString([(0, 0), (1, 0)]),
            LineString([(1, 0), (2, 1)]),
            LineString([(1, 0), (2, -1)]),
        ],
    )

    verbindingen = create_hydroobject_verbindingen(
        segmenten,
        _puntobjecten([]),
        tolerance=0,
    )

    assert {
        tuple(row)
        for row in verbindingen[["van_segment", "naar_segment"]].itertuples(
            index=False, name=None
        )
    } == {
        ("in:0001", "out-a:0001"),
        ("in:0001", "out-b:0001"),
    }


def test_two_incoming_and_one_outgoing_segments_create_two_directed_connections():
    segmenten = _segmenten(
        ["in-a:0001", "in-b:0001", "out:0001"],
        [
            LineString([(0, 1), (1, 0)]),
            LineString([(0, -1), (1, 0)]),
            LineString([(1, 0), (2, 0)]),
        ],
    )

    verbindingen = create_hydroobject_verbindingen(
        segmenten,
        _puntobjecten([]),
        tolerance=0,
    )

    assert {
        tuple(row)
        for row in verbindingen[["van_segment", "naar_segment"]].itertuples(
            index=False, name=None
        )
    } == {
        ("in-a:0001", "out:0001"),
        ("in-b:0001", "out:0001"),
    }


def test_three_outgoing_segments_create_a_tree_without_duplicate_connections():
    segmenten = _segmenten(
        ["out-a:0001", "out-b:0001", "out-c:0001"],
        [
            LineString([(1, 0), (2, 0)]),
            LineString([(1, 0), (2, 1)]),
            LineString([(1, 0), (2, -1)]),
        ],
    )

    verbindingen = create_hydroobject_verbindingen(
        segmenten,
        _puntobjecten([]),
        tolerance=0,
    )

    assert len(verbindingen) == 2
    assert {
        tuple(row)
        for row in verbindingen[["van_segment", "naar_segment"]].itertuples(
            index=False, name=None
        )
    } == {
        ("out-a:0001", "out-b:0001"),
        ("out-a:0001", "out-c:0001"),
    }
    assert not verbindingen.duplicated(
        ["van_segment", "naar_segment", "geometry"]
    ).any()
    assert not (verbindingen["van_segment"] == verbindingen["naar_segment"]).any()


def test_ambiguous_junction_uses_deterministic_main_route_with_n_minus_one_edges():
    segmenten = _segmenten(
        ["in-a:0001", "in-b:0001", "out-a:0001", "out-b:0001"],
        [
            LineString([(0, 0), (1, 0)]),
            LineString([(0, 1), (1, 0)]),
            LineString([(1, 0), (2, 0)]),
            LineString([(1, 0), (2, 1)]),
        ],
    )

    verbindingen = create_hydroobject_verbindingen(
        segmenten,
        _puntobjecten([]),
        tolerance=0,
    )

    assert len(verbindingen) == 3
    assert {
        tuple(row)
        for row in verbindingen[["van_segment", "naar_segment"]].itertuples(
            index=False, name=None
        )
    } == {
        ("in-a:0001", "out-a:0001"),
        ("in-a:0001", "out-b:0001"),
        ("in-b:0001", "out-a:0001"),
    }


def test_geometric_crossing_without_pointobject_does_not_create_connection():
    result = prepare_watersysteem(
        _hydroobjecten(),
        _puntobjecten([]),
        max_length=500,
    )

    assert result.hydroobject_verbinding.empty


def test_point_outside_tolerance_does_not_split_or_connect():
    result = prepare_watersysteem(
        _hydroobjecten().iloc[[0]],
        _puntobjecten([Point(25, 3)]),
        tolerance=2,
        max_length=500,
    )

    assert len(result.hydroobject_segmenten) == 1
    assert result.hydroobject_verbinding.empty


def test_endpoint_and_duplicate_points_do_not_create_empty_segments():
    result = split_hydroobjecten_at_points(
        _hydroobjecten().iloc[[0]],
        _puntobjecten([Point(0, 0), Point(25, 0), Point(25, 0)]),
        tolerance=0,
    )

    assert len(result.hydroobject_segmenten) == 2
    assert (result.hydroobject_segmenten.geometry.length > 0).all()
    assert result.hydroobject_verbinding.empty


def test_split_hydroobjecten_by_length_keeps_stable_identifiers_and_lengths():
    result = split_hydroobjecten_by_length(
        _hydroobjecten().iloc[[0]],
        max_length=30,
    )

    assert result.geometry.length.tolist() == [25.0, 25.0, 25.0, 25.0]
    assert result["bron_id"].tolist() == ["hydro-a"] * 4
    assert result["segment_id"].tolist() == [
        "hydro-a:0001",
        "hydro-a:0002",
        "hydro-a:0003",
        "hydro-a:0004",
    ]


def test_split_hydroobjecten_by_length_divides_long_lines_equally():
    hydroobjecten = _hydroobjecten().iloc[[0]].copy()
    hydroobjecten.geometry = [LineString([(0, 0), (600, 0)])]

    result = split_hydroobjecten_by_length(hydroobjecten, max_length=500)

    assert result.geometry.length.tolist() == [300.0, 300.0]


def test_secondary_connected_to_secondary_is_retained_once_with_source_fields():
    primair = _hydroobjecten_met_bron_ids(["primair-1"])
    primair.geometry = [LineString([(100, 0), (110, 0)])]
    secundair = _hydroobjecten_met_bron_ids(
        ["secundair-1", "secundair-2", "secundair-los"]
    )
    secundair.geometry = [
        LineString([(0, 0), (5, 0)]),
        LineString([(6, 0), (11, 0)]),
        LineString([(20, 0), (25, 0)]),
    ]

    verbonden, niet_verbonden = split_connected_secondary_hydroobjecten(
        secundair,
        primair,
        _bron_verbindingen([]),
    )

    assert verbonden["bron_id"].tolist() == ["secundair-1", "secundair-2"]
    assert niet_verbonden["bron_id"].tolist() == ["secundair-los"]
    assert verbonden["code"].tolist() == ["code-secundair-1", "code-secundair-2"]
    assert verbonden.crs == secundair.crs
    assert len(verbonden) + len(niet_verbonden) == len(secundair)


def test_secondary_connected_to_primary_and_secondary_is_retained_once():
    primair = _hydroobjecten_met_bron_ids(["primair-1", "primair-los"])
    secundair = _hydroobjecten_met_bron_ids(["secundair-1", "secundair-2"])
    primair.geometry = [
        LineString([(0, 0), (10, 0)]),
        LineString([(100, 0), (110, 0)]),
    ]
    secundair.geometry = [
        LineString([(11, 0), (20, 0)]),
        LineString([(21, 0), (30, 0)]),
    ]

    verbonden, niet_verbonden = split_connected_secondary_hydroobjecten(
        secundair,
        primair,
        _bron_verbindingen([]),
    )

    assert verbonden["bron_id"].tolist() == ["secundair-1", "secundair-2"]
    assert niet_verbonden.empty


def test_unknown_connection_identifier_is_ignored_and_warned(caplog):
    primair = _hydroobjecten_met_bron_ids(["primair-1"])
    secundair = _hydroobjecten_met_bron_ids(["secundair-1"])
    secundair.geometry = [LineString([(100, 0), (110, 0)])]
    verbindingen = _bron_verbindingen([("secundair-1", "onbekend")])

    verbonden, niet_verbonden = split_connected_secondary_hydroobjecten(
        secundair,
        primair,
        verbindingen,
    )

    assert verbonden.empty
    assert niet_verbonden["bron_id"].tolist() == ["secundair-1"]
    assert "unknown bron_id" in caplog.text


def test_secondary_with_internal_line_crossing_is_connected_without_endpoint():
    primair = _hydroobjecten_met_bron_ids(["primair-1"])
    primair.geometry = [LineString([(0, 0), (20, 0)])]
    secundair = _hydroobjecten_met_bron_ids(["secundair-1"])
    secundair.geometry = [LineString([(10, -5), (10, 5)])]

    verbonden, niet_verbonden = split_connected_secondary_hydroobjecten(
        secundair,
        primair,
        _bron_verbindingen([]),
    )

    assert verbonden["bron_id"].tolist() == ["secundair-1"]
    assert niet_verbonden.empty


def test_secondary_connection_tolerance_is_configurable():
    primair = _hydroobjecten_met_bron_ids(["primair-1"])
    primair.geometry = [LineString([(0, 0), (10, 0)])]
    secundair = _hydroobjecten_met_bron_ids(["secundair-1"])
    secundair.geometry = [LineString([(13, 0), (20, 0)])]

    verbonden, _ = split_connected_secondary_hydroobjecten(
        secundair,
        primair,
        _bron_verbindingen([]),
    )
    verbonden_met_3m, niet_verbonden = split_connected_secondary_hydroobjecten(
        secundair,
        primair,
        _bron_verbindingen([]),
        tolerance=3,
    )

    assert verbonden.empty
    assert verbonden_met_3m["bron_id"].tolist() == ["secundair-1"]
    assert niet_verbonden.empty


@pytest.mark.parametrize(
    ("bron_ids", "match"),
    [
        (["secundair-1", None], "without a usable bron_id"),
        (["secundair-1", "secundair-1"], "duplicate bron_id"),
    ],
)
def test_invalid_secondary_bron_ids_are_rejected_with_warning(
    bron_ids,
    match,
    caplog,
):
    with pytest.raises(ValueError, match=match):
        split_connected_secondary_hydroobjecten(
            _hydroobjecten_met_bron_ids(bron_ids),
            _hydroobjecten_met_bron_ids(["primair-1"]),
            _bron_verbindingen([]),
        )

    assert "bron_id" in caplog.text


def test_empty_secondary_input_preserves_schema_and_crs():
    secundair = _hydroobjecten_met_bron_ids([])

    verbonden, niet_verbonden = split_connected_secondary_hydroobjecten(
        secundair,
        _hydroobjecten_met_bron_ids(["primair-1"]),
        _bron_verbindingen([]),
    )

    assert verbonden.empty
    assert niet_verbonden.empty
    assert verbonden.columns.tolist() == secundair.columns.tolist()
    assert niet_verbonden.crs == secundair.crs


def test_prepare_watersysteem_excludes_secondary_from_segment_connections():
    primair = _hydroobjecten_met_bron_ids(["primair-1"])
    primair.geometry = [LineString([(0, 0), (20, 0)])]
    secundair = _hydroobjecten_met_bron_ids(["secundair-1"])
    secundair.geometry = [LineString([(20, 0), (30, 0)])]

    watersysteem = prepare_watersysteem(
        primair,
        _puntobjecten([]),
        hydroobject_secundair=secundair,
        max_length=10,
    )

    assert watersysteem.hydroobject_segmenten["bron_id"].tolist() == [
        "primair-1",
        "primair-1",
    ]
    assert watersysteem.hydroobject_verbinding[
        ["van_segment", "naar_segment", "van_bron_id", "naar_bron_id"]
    ].values.tolist() == [
        ["primair-1:0001", "primair-1:0002", "primair-1", "primair-1"]
    ]


def test_write_watersysteem_writes_exact_required_layers(hydamo_path, tmp_path):
    hydroobjecten = read_hydroobjecten(hydamo_path)
    primair = hydroobjecten[
        hydroobjecten["categorieoppwaterlichaam"] == "primair"
    ].copy()
    secundair = hydroobjecten[
        hydroobjecten["categorieoppwaterlichaam"] == "secundair"
    ].copy()
    punten = read_puntobjecten(hydamo_path)
    watersysteem = prepare_watersysteem(primair, punten, tolerance=2, max_length=30)
    output_path = tmp_path / "watersysteem.gpkg"

    result = write_watersysteem(
        hydroobject_primair=primair,
        hydroobject_secundair=secundair,
        watersysteem=watersysteem,
        output_path=output_path,
    )

    assert result.name == "watersysteem.gpkg"
    assert set(gpd.list_layers(result)["name"]) == {
        "hydroobject_primair",
        "hydroobject_secundair",
        "hydroobject_secundair_niet_verbonden",
        "hydroobject_segment",
        "hydroobject_verbinding",
        "layer_styles",
    }
    assert gpd.read_file(result, layer="hydroobject_primair").crs.to_epsg() == 28992
    assert gpd.read_file(result, layer="hydroobject_secundair").empty
    assert gpd.read_file(result, layer="hydroobject_secundair_niet_verbonden")[
        "categorieoppwaterlichaam"
    ].tolist() == ["secundair"]


def test_write_watersysteem_places_connected_secondary_in_connected_layer(tmp_path):
    primair = _hydroobjecten_met_bron_ids(["primair-1"])
    primair.geometry = [LineString([(0, 0), (10, 0)])]
    secundair = _hydroobjecten_met_bron_ids(["secundair-1", "secundair-los"])
    secundair.geometry = [
        LineString([(10, 0), (20, 0)]),
        LineString([(100, 0), (110, 0)]),
    ]
    watersysteem = prepare_watersysteem(
        primair,
        _puntobjecten([]),
        hydroobject_secundair=secundair,
        max_length=100,
    )
    output_path = tmp_path / "watersysteem.gpkg"

    write_watersysteem(
        hydroobject_primair=primair,
        hydroobject_secundair=secundair,
        watersysteem=watersysteem,
        output_path=output_path,
    )

    assert gpd.read_file(output_path, layer="hydroobject_secundair")[
        "bron_id"
    ].tolist() == ["secundair-1"]
    assert gpd.read_file(output_path, layer="hydroobject_secundair_niet_verbonden")[
        "bron_id"
    ].tolist() == ["secundair-los"]


def test_watersysteem_validation_requires_unconnected_secondary_layer(tmp_path):
    output_path = tmp_path / "onvolledig-watersysteem.gpkg"
    features = _hydroobjecten_met_bron_ids(["primair-1"])
    for index, layer_name in enumerate(
        (
            "hydroobject_primair",
            "hydroobject_secundair",
            "hydroobject_segment",
            "hydroobject_verbinding",
        )
    ):
        features.to_file(
            output_path,
            layer=layer_name,
            driver="GPKG",
            index=False,
            mode="w" if index == 0 else "a",
        )

    with pytest.raises(
        ValueError,
        match="hydroobject_secundair_niet_verbonden",
    ):
        workflow._validate_watersysteem_output(output_path)


def test_write_watersysteem_reuses_valid_existing_output(
    hydamo_path, tmp_path, monkeypatch
):
    hydroobjecten = read_hydroobjecten(hydamo_path)
    primair = hydroobjecten.iloc[[0]].copy()
    secundair = hydroobjecten.iloc[[1]].copy()
    watersysteem = prepare_watersysteem(primair, read_puntobjecten(hydamo_path))
    output_path = tmp_path / "watersysteem.gpkg"
    write_watersysteem(
        hydroobject_primair=primair,
        hydroobject_secundair=secundair,
        watersysteem=watersysteem,
        output_path=output_path,
    )
    monkeypatch.setattr(
        gpd.GeoDataFrame,
        "to_file",
        lambda *args, **kwargs: pytest.fail("valid output should be reused"),
    )

    result = write_watersysteem(
        hydroobject_primair=primair,
        hydroobject_secundair=secundair,
        watersysteem=watersysteem,
        output_path=output_path,
        overwrite=False,
    )

    assert result == output_path


def test_failed_write_cleans_temporary_file_and_preserves_existing_output(
    hydamo_path,
    tmp_path,
    monkeypatch,
):
    hydroobjecten = read_hydroobjecten(hydamo_path)
    primair = hydroobjecten.iloc[[0]].copy()
    secundair = hydroobjecten.iloc[[1]].copy()
    watersysteem = prepare_watersysteem(primair, read_puntobjecten(hydamo_path))
    output_path = tmp_path / "watersysteem.gpkg"
    write_watersysteem(
        hydroobject_primair=primair,
        hydroobject_secundair=secundair,
        watersysteem=watersysteem,
        output_path=output_path,
    )
    original = gpd.read_file(output_path, layer="hydroobject_segment")
    monkeypatch.setattr(
        workflow,
        "_validate_watersysteem_output",
        lambda path: (_ for _ in ()).throw(ValueError("temporary output is invalid")),
    )

    with pytest.raises(ValueError, match="temporary output is invalid"):
        write_watersysteem(
            hydroobject_primair=primair,
            hydroobject_secundair=secundair,
            watersysteem=watersysteem,
            output_path=output_path,
            overwrite=True,
        )

    assert not list(tmp_path.glob(".watersysteem.gpkg.*.gpkg"))
    assert len(gpd.read_file(output_path, layer="hydroobject_segment")) == len(original)
