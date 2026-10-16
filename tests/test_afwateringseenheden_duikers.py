"""Culvert route, classification, persistence and raster regression tests."""

from contextlib import closing
import sqlite3

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from shapely.geometry import LineString, Point, box

from waterlagen import _geopandas as wgpd
from waterlagen.afwateringseenheden import (
    Brandlaag,
    BrandlagenConfig,
    prepare_watersysteem,
    write_watersysteem,
    prepare_watersysteem_rasters,
    calculate_subcatchments,
)


def lines(geometries, ids=None):
    return gpd.GeoDataFrame(
        {"bron_id": ids or [f"line{i}" for i in range(len(geometries))]},
        geometry=geometries,
        crs=28992,
    )


def empty():
    return lines([])


def prepare(primary, culverts, **kwargs):
    return prepare_watersysteem(primary, empty(), duikersifonhevel=culverts, **kwargs)


def straight():
    return lines([LineString([(0, 5), (20, 5)])])


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("offset,matched", [(0, True), (0.5, True), (0.50001, False)])
def test_both_endpoints_inclusive_and_direction_independent(reverse, offset, matched):
    coordinates = [(5, 5 + offset), (15, 5 + offset)]
    if reverse:
        coordinates.reverse()
    result = prepare(straight(), lines([LineString(coordinates)]))
    segments = result.hydroobject_segmenten
    if matched:
        assert segments.length.tolist() == [5, 10, 5]
        assert segments.brandgeschikt.tolist() == [True, False, True]
        assert segments.doelgeschikt.tolist() == [True, False, True]
        assert result.duiker_controle.empty
    else:
        assert len(segments) == 1
        assert segments.brandgeschikt.all()
        assert "geen primair" in result.duiker_controle.reden.iloc[0]


@pytest.mark.parametrize(
    "last,reason",
    [
        ((15, 6), "slechts één"),
        ((15, 20), "slechts één"),
    ],
)
def test_half_match_has_no_partial_effect(last, reason):
    result = prepare(
        straight(), lines([LineString([(5, 5), last])]), max_aansluitlengte=100
    )
    assert result.hydroobject_segmenten.length.tolist() == [20]
    assert result.hydroobject_segmenten.doelgeschikt.all()
    assert reason in result.duiker_controle.reden.iloc[0]


def test_parallel_ambiguous_and_crossing_routes():
    primary = lines(
        [
            LineString([(0, 5), (20, 5)]),
            LineString([(0, 5.4), (20, 5.4)]),
            LineString([(10, 0), (10, 10)]),
        ]
    )
    result = prepare(primary, lines([LineString([(5, 5), (15, 5)])]))
    assert result.duiker_controle.empty
    excluded = result.hydroobject_segmenten.loc[
        ~result.hydroobject_segmenten.brandgeschikt
    ]
    assert excluded.bron_id.tolist() == ["line0"]
    ambiguous = prepare(primary, lines([LineString([(5, 5.2), (15, 5.2)])]))
    assert len(ambiguous.hydroobject_segmenten) == 3
    assert "meerdere" in ambiguous.duiker_controle.reden.iloc[0]


def test_multi_source_route_and_shared_node_candidates():
    primary = lines(
        [
            LineString([(0, 5), (10, 5)]),
            LineString([(10, 5), (20, 5)]),
            LineString([(10, 5), (10, 10)]),
        ]
    )
    primary["waterbeheercode"] = ["30", "80", "38"]
    result = prepare(primary, lines([LineString([(10, 5), (15, 5)])]))
    assert result.duiker_controle.empty
    assert result.hydroobject_segmenten.loc[
        ~result.hydroobject_segmenten.brandgeschikt
    ].waterbeheercode.tolist() == ["80"]
    result = prepare(primary, lines([LineString([(5, 5), (15, 5)])]))
    assert result.duiker_controle.empty
    assert (
        result.hydroobject_segmenten.loc[
            ~result.hydroobject_segmenten.brandgeschikt
        ].length.sum()
        == 10
    )


def test_disconnected_and_unusable_geometry_controls():
    primary = lines([LineString([(0, 5), (9, 5)]), LineString([(11, 5), (20, 5)])])
    result = prepare(primary, lines([LineString([(5, 5), (15, 5)]), Point(2, 5), None]))
    assert len(result.duiker_controle) == 3
    assert "aaneengesloten" in result.duiker_controle.reden.iloc[0]
    assert result.duiker_controle.reden.iloc[1:].str.contains("bruikbare").all()
    assert result.hydroobject_segmenten.doelgeschikt.all()


@pytest.mark.parametrize(
    "limit,expected", [(None, 20), (0, 20), (4, 20), (5, 10), (6, 10)]
)
@pytest.mark.parametrize("max_length", [500, 2])
def test_adjacent_length_before_maximum_split_and_no_recursion(
    limit, expected, max_length
):
    primary = lines(
        [
            LineString([(0, 5), (20, 5)]),
            LineString([(-5, 5), (0, 5)]),
            LineString([(20, 5), (25, 5)]),
        ]
    )
    result = prepare(
        primary,
        lines([LineString([(5, 5), (15, 5)])]),
        max_aansluitlengte=limit,
        max_length=max_length,
    )
    segments = result.hydroobject_segmenten
    assert segments.loc[segments.doelgeschikt].length.sum() == pytest.approx(expected)
    assert segments.loc[segments.brandgeschikt].length.sum() == 20
    assert segments.loc[segments.bron_id.ne("line0"), "doelgeschikt"].all()


def test_branch_lengths_and_physical_points():
    primary = lines(
        [
            LineString([(0, 5), (20, 5)]),
            LineString([(0, 5), (0, 8)]),
            LineString([(0, 5), (0, 15)]),
        ]
    )
    result = prepare(
        primary, lines([LineString([(0, 5), (5, 5)])]), max_aansluitlengte=3
    )
    segments = result.hydroobject_segmenten
    assert not segments.loc[segments.bron_id.eq("line1"), "doelgeschikt"].any()
    assert segments.loc[segments.bron_id.eq("line2"), "doelgeschikt"].all()
    result = prepare_watersysteem(
        straight(),
        lines([Point(3, 5)]),
        duikersifonhevel=lines([LineString([(5, 5), (15, 5)])]),
        max_aansluitlengte=2,
    )
    assert result.hydroobject_segmenten.doelgeschikt.tolist() == [
        True,
        False,
        False,
        True,
    ]


def test_new_culvert_cut_does_not_connect_crossing_source():
    primary = lines([LineString([(0, 5), (20, 5)]), LineString([(5, 5), (5, 15)])])
    result = prepare(primary, lines([LineString([(5, 5), (15, 5)])]))
    connections = result.hydroobject_verbinding
    assert connections.van_bron_id.eq(connections.naar_bron_id).all()
    result = prepare(
        primary, lines([LineString([(5, 5), (15, 5)])]), max_aansluitlengte=20
    )
    assert result.hydroobject_segmenten.loc[
        result.hydroobject_segmenten.bron_id.eq("line1"), "doelgeschikt"
    ].all()
    connected = prepare_watersysteem(
        primary,
        lines([Point(5, 5)]),
        duikersifonhevel=lines([LineString([(5, 5), (15, 5)])]),
    )
    assert connected.hydroobject_verbinding.van_bron_id.ne(
        connected.hydroobject_verbinding.naar_bron_id
    ).any()


@pytest.mark.parametrize("parameter", ["duiker_tolerance", "max_aansluitlengte"])
@pytest.mark.parametrize("value", [-1, float("inf"), float("nan")])
def test_invalid_settings(parameter, value):
    with pytest.raises(ValueError, match="finite and non-negative"):
        prepare(straight(), empty(), **{parameter: value})


def write(tmp_path, primary, result, secondary=None):
    return write_watersysteem(
        hydroobject_primair=primary,
        hydroobject_secundair=empty() if secondary is None else secondary,
        watersysteem=result,
        output_path=tmp_path / "watersysteem.gpkg",
    )


def test_snapshot_reuse_controls_recovery_and_stale_replacement(tmp_path, caplog):
    primary = straight()
    bad = lines([LineString([(5, 5), (15, 7)])])
    result = prepare(primary, bad)
    path = write(tmp_path, primary, result)
    original_time = path.stat().st_mtime_ns
    control_path = tmp_path / "controle.gpkg"
    assert "1 duikers" in caplog.text
    assert str(control_path) in caplog.text
    assert len(wgpd.read_file(control_path, layer="duikersifonhevel")) == 1
    control_path.unlink()
    write(tmp_path, primary, result)
    assert control_path.exists()
    assert path.stat().st_mtime_ns == original_time
    lines([Point(0, 0)]).to_file(control_path, layer="other_control")
    corrected = prepare(primary, lines([LineString([(5, 5), (15, 5)])]))
    write(tmp_path, primary, corrected)
    assert path.stat().st_mtime_ns != original_time
    assert wgpd.read_file(control_path, layer="duikersifonhevel").empty
    assert len(wgpd.read_file(control_path, layer="other_control")) == 1
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("DROP TABLE waterlagen_duikers")
    write(tmp_path, primary, corrected)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT signature FROM waterlagen_duikers").fetchone()


def ahn(tmp_path):
    path = tmp_path / "ahn.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=20,
        height=20,
        count=1,
        dtype="float32",
        crs=28992,
        transform=rasterio.transform.from_origin(0, 20, 1, 1),
    ) as destination:
        destination.write(np.full((20, 20), 10, dtype="float32"), 1)
    return path


@pytest.mark.parametrize("optional", [False, True])
def test_burn_target_fids_secondary_and_subcatchments(tmp_path, optional):
    primary = straight()
    secondary = lines([LineString([(10, 5), (10, 10)])], ["secondary"])
    result = prepare(primary, lines([LineString([(5, 5), (15, 5)])]))
    path = write(tmp_path, primary, result, secondary)
    assert wgpd.read_file(path, layer="hydroobject_primair_bron").length.sum() == 20
    assert wgpd.read_file(path, layer="hydroobject_primair").length.sum() == 10
    assert len(wgpd.read_file(path, layer="hydroobject_secundair")) == 1
    config = None
    if optional:
        source = tmp_path / "optional.gpkg"
        lines([box(0, 0, 20, 20)]).to_file(source, layer="optional")
        config = BrandlagenConfig(
            (Brandlaag(source, "optional"),), brandwaarde=-1, prioriteit=1
        )
    rasters = prepare_watersysteem_rasters(
        box(0, 0, 20, 20),
        burn_depth_m=2,
        ahn_vrt_path=ahn(tmp_path),
        watersysteem_path=path,
        output_dir=tmp_path / "rasters",
        resolution_m=1,
        brandlagen=config,
    )
    with (
        rasterio.open(rasters.dem_path) as dem,
        rasterio.open(rasters.hydroobject_segment_path) as targets,
    ):
        values, ids = dem.read(1), targets.read(1)
    assert values[15, 3] == 6
    assert values[15, 8] == (9 if optional else 10)
    assert values[15, 10] == 8  # Secondary still connects against full primary.
    assert set(np.unique(ids)) == {0, 1, 3}  # Stored FID gap retained.
    assert ids[15, 5] == 1  # Allowed upstream endpoint may touch this cell.
    assert ids[15, 6] == 0
    assert ids[15, 15] == 3
    subcatchments = calculate_subcatchments(rasters, watersysteem_path=path)
    assert set(subcatchments.subcatchments.segment_id) <= {"line0:0001", "line0:0003"}


def test_target_modes_and_adjacent_length_keep_burning(tmp_path):
    primary = lines([LineString([(0, 5), (20, 5)]), LineString([(0, 15), (20, 15)])])
    culverts = lines([LineString([(5, 5), (15, 5)]), LineString([(5, 15), (15, 15)])])
    source = ahn(tmp_path)
    arrays = []
    for i, (targets, limit) in enumerate(
        [(primary, None), (primary.iloc[:1], None), (primary, 5)]
    ):
        result = prepare_watersysteem(
            targets,
            empty(),
            hydroobject_primair=primary,
            duikersifonhevel=culverts,
            max_aansluitlengte=limit,
        )
        path = write(tmp_path / str(i), primary, result)
        rasters = prepare_watersysteem_rasters(
            box(0, 0, 20, 20),
            burn_depth_m=2,
            ahn_vrt_path=source,
            watersysteem_path=path,
            output_dir=tmp_path / "rasters",
            resolution_m=1,
        )
        with rasterio.open(rasters.dem_path) as dem:
            arrays.append(dem.read(1))
        with rasterio.open(rasters.hydroobject_segment_path) as raster:
            if limit is not None:
                assert not raster.read(1).any()
    np.testing.assert_array_equal(arrays[0], arrays[1])
    np.testing.assert_array_equal(arrays[0], arrays[2])


def test_geometry_distinguishes_routes_without_authority_preference():
    primary = lines(
        [
            LineString([(0, 0), (5, 2), (10, 0)]),
            LineString([(0, 0), (5, -2), (10, 0)]),
        ]
    )
    primary["waterbeheercode"] = ["30", "80"]
    culverts = lines([LineString([(0, 0), (5, -2), (10, 0)])])
    culverts["waterbeheercode"] = "30"
    result = prepare(primary, culverts)
    assert result.hydroobject_segmenten.brandgeschikt.tolist() == [True, False]
    assert result.duiker_controle.empty
    culverts.geometry = [LineString([(0, 0), (10, 0)])]
    result = prepare(primary, culverts)
    assert result.hydroobject_segmenten.brandgeschikt.all()
    assert "meerdere" in result.duiker_controle.reden.iloc[0]


def test_overlapping_culverts_keep_all_provenance_and_failed_match_has_no_effect():
    culverts = lines(
        [
            LineString([(5, 5), (12, 5)]),
            LineString([(10, 5), (15, 5)]),
            LineString([(1, 5), (3, 8)]),
        ],
        ["a", "b", "failed"],
    )
    result = prepare(straight(), culverts)
    assert result.hydroobject_segmenten.length.tolist() == [5, 5, 2, 3, 5]
    assert result.hydroobject_segmenten.duiker_ids.tolist() == [
        "[]",
        '["a"]',
        '["a", "b"]',
        '["b"]',
        "[]",
    ]
    assert result.duiker_controle.bron_id.tolist() == ["failed"]


@pytest.mark.parametrize("change", ["tolerance", "length", "control", "remove"])
def test_lower_writer_never_reuses_changed_culvert_settings(tmp_path, change):
    primary = straight()
    culverts = lines([LineString([(5, 5.4), (15, 5.4)])])
    first = prepare(primary, culverts)
    path = write(tmp_path, primary, first)
    original = path.stat().st_mtime_ns
    if change == "tolerance":
        second = prepare(primary, culverts, duiker_tolerance=0.3)
    elif change == "length":
        second = prepare(primary, culverts, max_aansluitlengte=5)
    elif change == "control":
        culverts.geometry = [LineString([(5, 5.4), (15, 8)])]
        second = prepare(primary, culverts)
    else:
        second = prepare_watersysteem(primary, empty())
    write(tmp_path, primary, second)
    assert path.stat().st_mtime_ns != original
    written = wgpd.read_file(path, layer="hydroobject_segment")
    if change == "length":
        assert not written.doelgeschikt.any()
    if change in ("control", "tolerance"):
        assert written.doelgeschikt.all()
        assert (
            len(wgpd.read_file(tmp_path / "controle.gpkg", layer="duikersifonhevel"))
            == 1
        )
    if change == "remove":
        assert len(written) == 1
        assert "doelgeschikt" not in written
