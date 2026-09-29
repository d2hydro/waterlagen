from itertools import combinations

import geopandas as gpd
import pandas as pd
import pytest
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import Point, box

from waterlagen.functioneel_landgebruik.bag_gebruiksfunctie import (
    determine_bag_functions,
)
from waterlagen.functioneel_landgebruik.bag_landgebruik import determine_bag_classes


@pytest.mark.parametrize(
    ("goals", "areas", "expected", "status"),
    [
        (["woonfunctie", "winkelfunctie"], [146, 80], "winkelfunctie", "gekozen"),
        (
            ["woonfunctie", "winkelfunctie", "kantoorfunctie"],
            [300, 50, 100],
            "kantoorfunctie",
            "gekozen",
        ),
        (
            ["woonfunctie", "woonfunctie", "winkelfunctie", "kantoorfunctie"],
            [300, 300, 50, 100],
            "kantoorfunctie",
            "gekozen",
        ),
        (
            ["woonfunctie", "winkelfunctie", "winkelfunctie", "kantoorfunctie"],
            [500, 60, 60, 100],
            "winkelfunctie",
            "gekozen",
        ),
        (
            ["woonfunctie", "woonfunctie", "winkelfunctie", "kantoorfunctie"],
            [300, 300, 100, 100],
            None,
            "nog te beoordelen",
        ),
        (
            ["woonfunctie", "woonfunctie", "kantoorfunctie"],
            [150, 100, 20],
            "kantoorfunctie",
            "gekozen",
        ),
        (
            [
                "onderwijsfunctie,sportfunctie",
                "bijeenkomstfunctie",
                "logiesfunctie",
                "sportfunctie",
            ],
            [9345, 237, 160, 1057],
            "onderwijsfunctie",
            "gekozen",
        ),
        (["sportfunctie,onderwijsfunctie"], [9345], "onderwijsfunctie", "gekozen"),
        (
            ["kantoorfunctie", "onderwijsfunctie", "kantoorfunctie"],
            [100, 150, 100],
            "kantoorfunctie",
            "gekozen",
        ),
        (["kantoorfunctie", "onderwijsfunctie"], [100, 100], None, "nog te beoordelen"),
        (
            ["woonfunctie", "overige gebruiksfunctie"],
            [150, 50],
            "woonfunctie",
            "gekozen",
        ),
        (
            ["woonfunctie"] * 3 + ["winkelfunctie"],
            [150, 150, 150, 50],
            "woonfunctie",
            "gekozen",
        ),
        (
            ["kantoorfunctie", "onderwijsfunctie"],
            [100, None],
            None,
            "nog te beoordelen",
        ),
        (["kantoorfunctie", "onderwijsfunctie"], [100, -10], None, "nog te beoordelen"),
        (["woonfunctie"], [None], "woonfunctie", "gekozen"),
        ([None], [100], None, "geen gebruiksdoel"),
        ([], [], None, "geen gebruiksdoel"),
    ],
)
def test_step3_keeps_source_and_explains_choice(goals, areas, expected, status):
    pand = gpd.GeoDataFrame(
        {"identificatie": ["p"]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:28992"
    )
    vbo = gpd.GeoDataFrame(
        {
            "identificatie": [str(i) for i in range(len(goals))],
            "pand_identificatie": ["p"] * len(goals),
            "gebruiksdoel": goals,
            "oppervlakte": areas,
        },
        geometry=[Point(0.5, 0.5)] * len(goals),
        crs=pand.crs,
    )
    original = vbo.copy()
    result = determine_bag_functions(pand, vbo)
    assert result.iloc[0]["gekozen_pandfunctie"] == expected
    assert result.iloc[0]["functiekeuze_status"] == status
    assert result.iloc[0]["reden_functiekeuze"]
    if result.iloc[0]["regel_functiekeuze"] == "grootste niet-woonoppervlakte":
        assert "woonfunctie:" not in result.iloc[0]["vergeleken_oppervlakten"]
        assert "wel voor de bouwlagen" in result.iloc[0]["reden_functiekeuze"]
    multiple = any(isinstance(goal, str) and "," in goal for goal in goals)
    if multiple:
        reason = result.iloc[0]["reden_functiekeuze"]
        assert "→ onderwijsfunctie volgens prioriteit" in reason
        assert "onderwijsfunctie" in reason and "sportfunctie" in reason
        assert "bijeenkomstfunctie" not in reason
    if goals == ["kantoorfunctie", "onderwijsfunctie"] and areas == [100, 100]:
        assert result.iloc[0]["reden_functiekeuze"] == (
            "kantoorfunctie: 100 m²; onderwijsfunctie: 100 m². "
            "Gelijke grootste oppervlakte: voorrang nog te bepalen."
        )
    if goals == ["kantoorfunctie", "onderwijsfunctie"] and areas == [100, None]:
        assert (
            "VBO 1 (onderwijsfunctie): oppervlakte ontbreekt"
            in result.iloc[0]["reden_functiekeuze"]
        )
    if goals == ["woonfunctie"] * 3 + ["winkelfunctie"]:
        assert "appartementencomplex" in result.iloc[0]["reden_functiekeuze"]
    assert_geodataframe_equal(vbo, original)
    assert_geodataframe_equal(result[list(pand.columns)], pand)
    assert "code" not in result and "aantal_verdiepingen" not in result
    empty = determine_bag_functions(pand.iloc[:0], vbo)
    assert empty.empty and "functiekeuze_status" in empty


def classify_functions(goals, areas, *, shared=False):
    pand = gpd.GeoDataFrame(
        {
            "identificatie": ["p"],
            "bron_aantal_vbo": [len(goals)],
            "berekend_aantal_bouwlagen": [1],
            "som_vbo_oppervlakte_m2": [100],
        },
        geometry=[box(0, 0, 10, 10)],
        crs="EPSG:28992",
    )
    vbo = gpd.GeoDataFrame(
        {
            "identificatie": [str(i) for i in range(len(goals))],
            "pand_identificatie": ["p,q" if shared else "p"] * len(goals),
            "gebruiksdoel": goals,
            "oppervlakte": areas,
        },
        geometry=[Point(1, 1)] * len(goals),
        crs=pand.crs,
    )
    return determine_bag_functions(pand, vbo)


@pytest.mark.parametrize("residential_count", [0, 1, 3])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    "goals,areas,expected",
    [
        (["winkelfunctie"] * 2, [30, 40], "winkelfunctie"),
        ([None, None], [20, 30], None),
        (["overige gebruiksfunctie"] * 2, [20, 30], "overige gebruiksfunctie"),
        (["overige gebruiksfunctie", None], [20, 900], "overige gebruiksfunctie"),
        (["overige gebruiksfunctie", None], [120, 900], "overige gebruiksfunctie"),
        (["winkelfunctie", None], [20, 900], "winkelfunctie"),
        (["winkelfunctie", None], [20, None], "winkelfunctie"),
        (["overige gebruiksfunctie", "winkelfunctie"], [99, 20], "winkelfunctie"),
        (
            ["overige gebruiksfunctie", "winkelfunctie"],
            [100, 20],
            "overige gebruiksfunctie",
        ),
        (
            ["overige gebruiksfunctie", "winkelfunctie"],
            [101, 20],
            "overige gebruiksfunctie",
        ),
        (["overige gebruiksfunctie", "winkelfunctie"], [100, 120], "winkelfunctie"),
        (["overige gebruiksfunctie", "winkelfunctie"], [99, 99], "winkelfunctie"),
        (["overige gebruiksfunctie", "winkelfunctie"], [100, 100], None),
        (["winkelfunctie", "kantoorfunctie"], [100, 100], None),
        (
            [None, "overige gebruiksfunctie", "winkelfunctie"],
            [1000, 90, 20],
            "winkelfunctie",
        ),
        (
            [None, "winkelfunctie", "kantoorfunctie"],
            [1000, 100, 100],
            None,
        ),
        (
            ["overige gebruiksfunctie"] * 2 + ["winkelfunctie"],
            [50, 50, 80],
            "overige gebruiksfunctie",
        ),
        (
            ["winkelfunctie"] * 2 + ["kantoorfunctie"],
            [60, 60, 100],
            "winkelfunctie",
        ),
    ],
)
def test_candidate_ranking_in_all_building_branches(
    residential_count, reverse, goals, areas, expected
):
    goals = ["woonfunctie"] * residential_count + goals
    areas = [10000] * residential_count + areas
    if reverse:
        goals = goals[::-1]
        areas = areas[::-1]
    result = classify_functions(goals, areas).iloc[0]
    assert result["gekozen_pandfunctie"] == expected
    candidates = [goal for goal in goals if goal != "woonfunctie"]
    if all(goal is None for goal in candidates):
        assert result["functiekeuze_status"] == "geen gebruiksdoel"
    elif expected is None:
        assert result["functiekeuze_status"] == "nog te beoordelen"
        assert result["regel_functiekeuze"] == "gelijke grootste oppervlakten"
    else:
        assert result["functiekeuze_status"] == "gekozen"
    assert "woonfunctie:" not in result["vergeleken_oppervlakten"]


@pytest.mark.parametrize("residential_count", [1, 2, 3, 4])
@pytest.mark.parametrize("other", [None, "overige gebruiksfunctie", "winkelfunctie"])
@pytest.mark.parametrize("area", [None, 0, 99, 100, 101, 10000])
def test_one_non_residential_vbo_ignores_floor_area(residential_count, other, area):
    goals = ["woonfunctie"] * residential_count + [other]
    areas = [100] * residential_count + [area]
    functions = classify_functions(goals, areas)
    expected = "woonfunctie"
    if residential_count <= 2 and other == "winkelfunctie":
        expected = "winkelfunctie"
    assert functions.iloc[0]["gekozen_pandfunctie"] == expected
    classes = determine_bag_classes(functions)
    expected_code = 4 if residential_count >= 3 else 1
    if expected == "winkelfunctie":
        expected_code = 29
    assert classes.iloc[0]["lgb_code_binnendijks"] == expected_code


@pytest.mark.parametrize("count", [1, 3, 4, 5])
def test_only_residential_vbos_produce_house_or_apartments(count):
    functions = classify_functions(["woonfunctie"] * count, [100] * count)
    classes = determine_bag_classes(functions)
    assert functions.iloc[0]["gekozen_pandfunctie"] == "woonfunctie"
    assert classes.iloc[0]["lgb_code_binnendijks"] == (1 if count <= 3 else 4)


@pytest.mark.parametrize("missing", [None, pd.NA, float("nan"), "", "  "])
def test_missing_goal_representations(missing):
    result = classify_functions(["woonfunctie", missing], [100, 20]).iloc[0]
    assert result["gekozen_pandfunctie"] == "woonfunctie"
    result = classify_functions(["winkelfunctie", missing], [100, 200]).iloc[0]
    assert result["gekozen_pandfunctie"] == "winkelfunctie"


@pytest.mark.parametrize("invalid", [None, 0, -1, float("inf"), "invalid"])
def test_invalid_candidate_area_keeps_ranking_open(invalid):
    result = classify_functions(["winkelfunctie", "kantoorfunctie"], [100, invalid])
    assert result.iloc[0]["regel_functiekeuze"] == "oppervlakte ontbreekt of ongeldig"


def test_shared_area_and_unknown_goals_stay_unresolved():
    result = classify_functions(
        ["winkelfunctie", "kantoorfunctie"], [100, 200], shared=True
    )
    assert result.iloc[0]["regel_functiekeuze"] == "verblijfsobject in meerdere panden"
    for unknown in ["onbekend", "winkelfunctie,onbekend"]:
        result = classify_functions(["woonfunctie", unknown], [100, 200])
        assert result.iloc[0]["functiekeuze_status"] == "nog te beoordelen"


@pytest.mark.parametrize(
    "higher,lower",
    list(
        combinations(
            [
                "gezondheidszorgfunctie",
                "winkelfunctie",
                "kantoorfunctie",
                "industriefunctie",
                "woonfunctie",
                "logiesfunctie",
                "onderwijsfunctie",
                "sportfunctie",
                "bijeenkomstfunctie",
                "celfunctie",
                "overige gebruiksfunctie",
            ],
            2,
        )
    ),
)
@pytest.mark.parametrize("reverse", [False, True])
def test_all_vbo_priority_pairs(higher, lower, reverse):
    functions = [higher, lower]
    if reverse:
        functions.reverse()
    result = classify_functions([",".join(functions)], [100]).iloc[0]
    assert result["gekozen_pandfunctie"] == higher
    assert set(result["alle_bag_gebruiksdoelen"].split(",")) == {higher, lower}
    assert f"→ {higher} volgens prioriteit" in result["reden_functiekeuze"]


@pytest.mark.parametrize(
    "value,expected",
    [
        (" WINKELFUNCTIE , woonfunctie, winkelfunctie, ", "winkelfunctie"),
        ("woonfunctie,woonfunctie", "woonfunctie"),
        (", ,", None),
        ("woonfunctie,logiesfunctie,gezondheidszorgfunctie", "gezondheidszorgfunctie"),
        ("onbekend,gezondheidszorgfunctie", None),
    ],
)
def test_priority_normalization_and_unknown_goals(value, expected):
    result = classify_functions([value], [100]).iloc[0]
    assert result["gekozen_pandfunctie"] == expected
    if "onbekend" in value:
        assert result["functiekeuze_status"] == "nog te beoordelen"
        assert "onbekend" in result["reden_functiekeuze"]


@pytest.mark.parametrize(
    "goals,areas,expected",
    [
        (["woonfunctie,winkelfunctie", "kantoorfunctie"], [200, 20], "winkelfunctie"),
        (["woonfunctie,logiesfunctie", "kantoorfunctie"], [200, 20], "kantoorfunctie"),
        (["woonfunctie"] * 3 + ["woonfunctie,winkelfunctie"], [100] * 4, "woonfunctie"),
        (
            ["woonfunctie"] * 2 + ["woonfunctie,winkelfunctie"] * 2,
            [100] * 4,
            "winkelfunctie",
        ),
        (
            ["onderwijsfunctie,sportfunctie", "onderwijsfunctie", "kantoorfunctie"],
            [60, 60, 100],
            "onderwijsfunctie",
        ),
        (["onderwijsfunctie,sportfunctie", "kantoorfunctie"], [100, 100], None),
    ],
)
def test_selected_goals_drive_building_counts_and_area_totals(goals, areas, expected):
    result = classify_functions(goals, areas).iloc[0]
    assert result["gekozen_pandfunctie"] == expected
    if len(goals) == 3:
        assert "onderwijsfunctie: 120 m²" in result["vergeleken_oppervlakten"]
        assert "sportfunctie:" not in result["vergeleken_oppervlakten"]
    if expected is None:
        assert result["regel_functiekeuze"] == "gelijke grootste oppervlakten"
