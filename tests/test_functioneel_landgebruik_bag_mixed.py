import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from waterlagen.functioneel_landgebruik.bag_gebruiksfunctie import (
    determine_bag_functions,
)


@pytest.mark.parametrize(
    ("doelen", "areas", "expected", "exception"),
    [
        (["woonfunctie", "winkelfunctie"], [150, 50], "winkelfunctie", True),
        (["winkelfunctie", "woonfunctie"], [50, 150], "winkelfunctie", True),
        (
            ["woonfunctie", "woonfunctie", "kantoorfunctie"],
            [150, 150, 50],
            "kantoorfunctie",
            True,
        ),
        (
            ["woonfunctie"] * 3 + ["winkelfunctie"],
            [150, 150, 150, 50],
            None,
            False,
        ),
        (["woonfunctie", "overige gebruiksfunctie"], [150, 50], "woonfunctie", False),
        (["overige gebruiksfunctie", "woonfunctie"], [500, 50], "woonfunctie", False),
        (
            ["woonfunctie"] * 3 + ["overige gebruiksfunctie"] * 2,
            [50, 50, 50, 200, 200],
            "woonfunctie",
            False,
        ),
        (["overige gebruiksfunctie"], [150], "overige gebruiksfunctie", False),
        (["woonfunctie,overige gebruiksfunctie"], [150], None, False),
        (["woonfunctie", None], [150, 50], None, False),
        (
            ["woonfunctie", "winkelfunctie,kantoorfunctie"],
            [150, 50],
            None,
            False,
        ),
        (
            ["woonfunctie", "winkelfunctie", "kantoorfunctie"],
            [150, 50, 30],
            "winkelfunctie",
            False,
        ),
        (["winkelfunctie"], [50], "winkelfunctie", False),
    ],
)
def test_mixed_residential_exception(doelen, areas, expected, exception):
    pand = gpd.GeoDataFrame(
        {"identificatie": ["p"], "status": ["Pand in gebruik"]},
        geometry=[box(0, 0, 10, 10)],
        crs="EPSG:28992",
    )
    vbo = gpd.GeoDataFrame(
        {
            "identificatie": [str(i) for i in range(len(doelen))],
            "pand_identificatie": ["p"] * len(doelen),
            "gebruiksdoel": doelen,
            "oppervlakte": areas,
        },
        geometry=[Point(1, 1)] * len(doelen),
        crs=pand.crs,
    )
    result = determine_bag_functions(pand, vbo).iloc[0]
    assert result["gekozen_pandfunctie"] == expected
    assert (result["regel_functiekeuze"] == "wonen met één andere functie") == exception
