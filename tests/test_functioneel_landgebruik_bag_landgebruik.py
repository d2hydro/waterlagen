import geopandas as gpd
import pandas as pd
import pytest
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import box

from waterlagen.functioneel_landgebruik.bag_gebruiksfunctie import (
    determine_bag_functions,
)
from waterlagen.functioneel_landgebruik.bag_landgebruik import determine_bag_classes
from waterlagen.functioneel_landgebruik.bag_verdiepingen import determine_bag_floors


@pytest.mark.parametrize(
    "function,count,floors,area,status,expected",
    [
        ("woonfunctie", 3, 1, 90, "gekozen", 1),
        ("woonfunctie", 3, 2, 180, "gekozen", 2),
        ("woonfunctie", 3, 5, 450, "gekozen", 3),
        ("woonfunctie", 4, None, None, "gekozen", 4),
        ("winkelfunctie", 4, 4, 226, "gekozen", 31),
        ("onderwijsfunctie", 4, 3, 10799, "gekozen", 25),
        (None, 4, 3, 10799, "nog te beoordelen", None),
        ("kantoorfunctie", 1, None, None, "gekozen", None),
        ("overige gebruiksfunctie", 1, 1, 100, "gekozen", 33),
        ("overige gebruiksfunctie", 1, 2, 101, "gekozen", 32),
        ("overige gebruiksfunctie", 2, 2, 150, "gekozen", None),
        ("overige gebruiksfunctie", 1, None, None, "gekozen", None),
        (None, 0, None, None, "geen gebruiksdoel", 34),
    ]
    + [
        (function, 1, floor, 100, "gekozen", base + floor - 1)
        for function, base in [
            ("bijeenkomstfunctie", 5),
            ("celfunctie", 8),
            ("gezondheidszorgfunctie", 11),
            ("industriefunctie", 14),
            ("kantoorfunctie", 17),
            ("logiesfunctie", 20),
            ("onderwijsfunctie", 23),
            ("sportfunctie", 26),
            ("winkelfunctie", 29),
        ]
        for floor in [1, 2, 3]
    ],
)
def test_note_codes_and_unresolved_choices(
    function, count, floors, area, status, expected
):
    panden = gpd.GeoDataFrame(
        {
            "gekozen_pandfunctie": [function],
            "bron_aantal_vbo": [count],
            "berekend_aantal_bouwlagen": [floors],
            "som_vbo_oppervlakte_m2": [area],
            "functiekeuze_status": [status],
        },
        geometry=[box(0, 0, 10, 10)],
        crs="EPSG:28992",
    )
    original = panden.copy()
    result = determine_bag_classes(panden)
    assert_geodataframe_equal(panden, original)
    assert_geodataframe_equal(result[list(panden.columns)], original)
    row = result.iloc[0]
    if expected is None:
        assert pd.isna(row["lgb_code_binnendijks"])
        assert pd.isna(row["lgb_code_buitendijks"])
        assert row["klasse_status"] == "nog te beoordelen"
    else:
        assert row["lgb_code_binnendijks"] == expected
        assert row["lgb_code_buitendijks"] == expected + 128
        assert row["klasse_status"] == "ingedeeld"
        assert row["lgb_omschrijving"]
    assert row["reden_klasse"]
    assert determine_bag_classes(panden.iloc[:0]).empty


@pytest.mark.parametrize(
    "goals,areas,expected",
    [
        (["overige gebruiksfunctie"] * 2, [60, 60], 32),
        (["overige gebruiksfunctie"] * 4, [25, 25, 25, 25], 33),
        (["overige gebruiksfunctie"] * 2, [40, 40], 33),
        (["overige gebruiksfunctie"] * 2, [60, None], None),
        (["overige gebruiksfunctie"] * 2, [60, -1], None),
        (["woonfunctie", "overige gebruiksfunctie"], [50, 150], 2),
        (["kantoorfunctie", "overige gebruiksfunctie"], [150, 50], 18),
        (["kantoorfunctie", "overige gebruiksfunctie"], [50, 150], None),
        (
            ["woonfunctie", "woonfunctie", "winkelfunctie", "kantoorfunctie"],
            [300, 300, 50, 100],
            19,
        ),
    ],
)
def test_other_use_total_after_function_selection(goals, areas, expected):
    panden = gpd.GeoDataFrame(
        {"identificatie": ["p1"], "bron_aantal_vbo": [len(goals)]},
        geometry=[box(0, 0, 10, 10)],
        crs="EPSG:28992",
    )
    objects = gpd.GeoDataFrame(
        {
            "identificatie": [f"v{i}" for i in range(len(goals))],
            "pand_identificatie": ["p1"] * len(goals),
            "gebruiksdoel": goals,
            "oppervlakte": areas,
        },
        geometry=[box(0, 0, 1, 1).centroid] * len(goals),
        crs=panden.crs,
    )
    functions = determine_bag_functions(panden, objects)
    floors = determine_bag_floors(functions, objects)
    result = determine_bag_classes(floors).iloc[0]
    if expected is None:
        assert pd.isna(result.lgb_code_binnendijks)
        assert result.klasse_status == "nog te beoordelen"
    else:
        assert result.lgb_code_binnendijks == expected
        assert result.lgb_code_buitendijks == expected + 128
        assert result.som_vbo_oppervlakte_m2 == sum(areas)
