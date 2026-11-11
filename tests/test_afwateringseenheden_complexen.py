"""Functional tests for complete parallel routes and unchanged burning."""

from pathlib import Path
import sqlite3
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET

import geopandas as gpd
import pandas as pd
import numpy as np
import pytest
import rasterio
from shapely import force_2d, reverse
from shapely.geometry import LineString, Point, box

from waterlagen import _geopandas as wgpd
from waterlagen.afwateringseenheden import (
    prepare_watersysteem,
    prepare_watersysteem_rasters,
)
from test_afwateringseenheden_duikers import ahn, empty, lines, write


def parallel(length=10, count=3):
    # Distinct collinear vertices create three physical paths with exact lengths.
    routes = [LineString([(2, 10), (7, 10 + y), (12, 10)]) for y in [-3, 0, 3][:count]]
    primary = lines(
        routes + [LineString([(0, 10), (2, 10)]), LineString([(12, 10), (19, 10)])]
    )
    points = lines([Point(7, 10 + y) for y in [-3, 0, 3][:count]])
    points["objecttype"] = "stuw"
    return primary, points


@pytest.mark.parametrize(
    "maximum,expected", [(0, False), (11, False), (12, True), (100, True)]
)
@pytest.mark.parametrize("max_length", [5, 25, 500])
@pytest.mark.parametrize("reversed_input", [False, True])
def test_parallel_stuwen(maximum, expected, max_length, reversed_input):
    primary, points = parallel()
    if reversed_input:
        primary = primary.iloc[::-1].copy()
        primary.geometry = primary.geometry.map(reverse)
        points = points.iloc[::-1]
    result = prepare_watersysteem(
        primary,
        points,
        tolerance=0,
        max_length=max_length,
        max_complex_routelengte=maximum,
    )
    segments = result.hydroobject_segmenten
    assert (
        segments.loc[
            segments.bron_id.isin(["line0", "line1", "line2"]), "afwateringsdoel"
        ]
        .eq(not expected)
        .all()
    )
    assert segments.loc[
        segments.bron_id.isin(["line3", "line4"]), "afwateringsdoel"
    ].all()
    assert segments.afwateringsdoel.equals(segments.doelgeschikt)


@pytest.mark.parametrize(
    "length,expected", [(99.999, True), (100, True), (100.001, False)]
)
def test_inclusive_full_route_length(length, expected):
    # Two routes of identical exact length, sharing portals ten metres apart.
    height = np.sqrt((length / 2) ** 2 - 25)
    primary = lines(
        [
            LineString([(0, 0), (5, height), (10, 0)]),
            LineString([(0, 0), (5, -height), (10, 0)]),
            LineString([(-1, 0), (0, 0)]),
            LineString([(10, 0), (11, 0)]),
        ]
    )
    points = lines([Point(5, height), Point(5, -height)])
    points["objecttype"] = "stuw"
    result = prepare_watersysteem(primary, points, tolerance=0, max_length=20)
    assert (
        result.hydroobject_segmenten.query("bron_id in ['line0','line1']")
        .afwateringsdoel.eq(not expected)
        .all()
    )


def test_missing_work_keeps_entire_group():
    primary, points = parallel()
    result = prepare_watersysteem(primary, points.iloc[:2], tolerance=0)
    assert result.hydroobject_segmenten.afwateringsdoel.all()


@pytest.mark.parametrize(
    "point_types,expected_exclusion",
    [
        (("meetpunt", "meetpunt"), False),
        (("stuw", "meetpunt"), False),
        (("stuw", "gemaal"), True),
        (("gemaal", "gemaal"), True),
        (None, False),
    ],
)
def test_only_registered_point_structures_count_on_parallel_routes(
    point_types, expected_exclusion
):
    # Same geometry as the review reproduction: ordinary points may split lines
    # but cannot supply the required structure on a route.
    primary = lines(
        [
            LineString([(0, 0), (5, 3), (10, 0)]),
            LineString([(0, 0), (5, -3), (10, 0)]),
            LineString([(-5, 0), (0, 0)]),
            LineString([(10, 0), (15, 0)]),
        ],
        ["boven", "onder", "west", "oost"],
    )
    points = lines([Point(5, 3), Point(5, -3)], ["punt_boven", "punt_onder"])
    if point_types is not None:
        points["objecttype"] = point_types
        points["bronlaag"] = point_types
    result = prepare_watersysteem(primary, points, tolerance=0)
    segments = result.hydroobject_segmenten
    assert (
        segments.loc[segments.bron_id.isin(["boven", "onder"]), "afwateringsdoel"]
        .eq(not expected_exclusion)
        .all()
    )
    assert segments.loc[
        segments.bron_id.isin(["west", "oost"]), "afwateringsdoel"
    ].all()


def reference():
    folder = Path(__file__).parent / "data/input/afwateringseenheden/complexen"
    primary = wgpd.read_file(folder / "hydroobject.geojson")
    primary.geometry = primary.geometry.map(force_2d)
    primary = primary.loc[primary.categorieoppwaterlichaam.eq("primair")].copy()
    culverts = wgpd.read_file(folder / "duikersifonhevel.geojson")
    points = wgpd.read_file(folder / "stuw.geojson")
    # The raw fixture omits the source reader's objecttype column.
    points["objecttype"] = "stuw"
    return primary, points, culverts


@pytest.mark.parametrize("max_length", [5, 25, 500])
@pytest.mark.parametrize("permuted", [False, True])
def test_six_real_reference_objects(max_length, permuted):
    primary, points, culverts = reference()
    if permuted:
        primary = primary.iloc[::-1].copy()
        primary.geometry = primary.geometry.map(reverse)
        culverts = culverts.iloc[::-1].copy()
        culverts.geometry = culverts.geometry.map(reverse)
    result = prepare_watersysteem(
        primary, points, duikersifonhevel=culverts, max_length=max_length
    )
    segments = result.hydroobject_segmenten
    prefixes = (
        "{79EFF4AA",
        "{C8EB0C9C",
        "{8BE0F5B4",
        "{7CF6E234",
        "{3847031A",
        "{45DC2D68",
    )
    selected = segments.bron_id.str.startswith(prefixes)
    assert segments.loc[selected, "bron_id"].nunique() == 6
    assert not segments.loc[selected, "afwateringsdoel"].any()
    assert segments.loc[~selected, "afwateringsdoel"].all()


def test_export_cache_style_and_real_burn_raster(tmp_path):
    primary, points = parallel()
    culverts = lines([LineString([(3, 9.4), (5, 8.2)])])
    source = ahn(tmp_path)
    arrays = []
    target_arrays = []
    evidence = []
    burn_flags = []
    path = None
    for maximum in (0, 100, 0):
        result = prepare_watersysteem(
            primary,
            points,
            duikersifonhevel=culverts,
            tolerance=0,
            max_complex_routelengte=maximum,
        )
        burn_flags.append(result.hydroobject_segmenten.brandgeschikt.tolist())
        path = write(tmp_path / "output", primary, result)
        shutil.copyfile(path, tmp_path / f"watersysteem_{maximum}.gpkg")
        written = wgpd.read_file(path, layer="hydroobject_segment", fid_as_index=True)
        assert written.segment_id.tolist() == written.index.tolist()
        assert written.afwateringsdoel.equals(written.doelgeschikt)
        assert not written.afwateringsdoel.isna().any()
        assert written.loc[
            written.bron_id.isin(["line0", "line1", "line2"]), "afwateringsdoel"
        ].any() == (maximum == 0)
        rasters = prepare_watersysteem_rasters(
            box(0, 0, 20, 20),
            burn_depth_m=2,
            ahn_vrt_path=source,
            watersysteem_path=path,
            output_dir=tmp_path / "rasters",
            resolution_m=1,
        )
        with rasterio.open(rasters.dem_path) as raster:
            arrays.append(raster.read(1))
            evidence.append(
                {
                    "maximum": maximum,
                    "pixels_sha256": hashlib.sha256(arrays[-1].tobytes()).hexdigest(),
                    "valid_mask_sha256": hashlib.sha256(
                        raster.read_masks(1).tobytes()
                    ).hexdigest(),
                    "transform": list(raster.transform),
                    "crs": str(raster.crs),
                }
            )
        shutil.copyfile(rasters.dem_path, tmp_path / f"dem_{len(arrays)}.tif")
        with rasterio.open(rasters.hydroobject_segment_path) as raster:
            target_arrays.append(raster.read(1))
    assert burn_flags[0] == burn_flags[1] == burn_flags[2]
    assert any(burn_flags[0]) and not all(burn_flags[0])
    (tmp_path / "rastervergelijking.json").write_text(json.dumps(evidence, indent=2))
    assert len({e["valid_mask_sha256"] for e in evidence}) == 1
    np.testing.assert_array_equal(arrays[0], arrays[1])
    np.testing.assert_array_equal(arrays[0], arrays[2])
    assert not np.array_equal(target_arrays[0], target_arrays[1])
    np.testing.assert_array_equal(target_arrays[0], target_arrays[2])
    with sqlite3.connect(path) as connection:
        styles = connection.execute(
            "SELECT styleQML FROM layer_styles WHERE f_table_name='hydroobject_segment' AND useAsDefault=1"
        ).fetchall()
    assert len(styles) == 1
    renderer = ET.fromstring(styles[0][0]).find("renderer-v2")
    assert renderer.get("attr") == "afwateringsdoel"
    assert {c.get("value") for c in renderer.find("categories")} == {"0", "1"}
    assert "255,140,0,255" in styles[0][0]


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_invalid_limit(value):
    with pytest.raises(ValueError, match="max_complex_routelengte"):
        prepare_watersysteem(empty(), empty(), max_complex_routelengte=value)


def test_whole_source_protection_and_external_side_branch():
    primary, points = parallel()
    primary.loc[3, "bron_id"] = "line0"
    result = prepare_watersysteem(primary, points, tolerance=0)
    assert result.hydroobject_segmenten.afwateringsdoel.all()
    primary, points = parallel()
    side = lines([LineString([(7, 7), (7, 1)])], ["side"])
    primary = gpd.GeoDataFrame(
        pd.concat([primary, side], ignore_index=True), crs=primary.crs
    )
    result = prepare_watersysteem(primary, points, tolerance=0)
    segments = result.hydroobject_segmenten
    assert not segments.loc[
        segments.bron_id.isin(["line0", "line1", "line2"]), "afwateringsdoel"
    ].any()
    assert segments.loc[segments.bron_id.eq("side"), "afwateringsdoel"].all()


def test_one_long_route_prevents_selecting_short_pair():
    primary, points = parallel()
    primary.loc[2, "geometry"] = LineString([(2, 10), (7, 80), (12, 10)])
    points.loc[2, "geometry"] = Point(7, 80)
    result = prepare_watersysteem(primary, points, tolerance=0, max_length=5)
    assert result.hydroobject_segmenten.afwateringsdoel.all()


def test_duplicate_work_identity_does_not_count_on_several_routes():
    primary, points = parallel()
    points["bron_id"] = "same_work"
    result = prepare_watersysteem(primary, points, tolerance=0)
    assert result.hydroobject_segmenten.afwateringsdoel.all()
