import geopandas as gpd
import pytest
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import Point, box

from waterlagen.functioneel_landgebruik.bag_gebruiksfunctie import (
    determine_bag_functions,
)


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
            None,
            "nog te beoordelen",
        ),
        (["sportfunctie,onderwijsfunctie"], [9345], None, "nog te beoordelen"),
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
            None,
            "nog te beoordelen",
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
        assert "9.345 m² niet uitgesplitst" in reason
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
        assert result.iloc[0]["reden_functiekeuze"] == (
            "3 woon-VBO’s + 1 winkel-VBO: voorrang bij meer dan 3 VBO’s nog te bepalen."
        )
    assert_geodataframe_equal(vbo, original)
    assert_geodataframe_equal(result[list(pand.columns)], pand)
    assert "code" not in result and "aantal_verdiepingen" not in result
    empty = determine_bag_functions(pand.iloc[:0], vbo)
    assert empty.empty and "functiekeuze_status" in empty
