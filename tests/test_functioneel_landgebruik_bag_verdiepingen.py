import geopandas as gpd
import pandas as pd
import pytest
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import Point, box

from waterlagen.functioneel_landgebruik.bag_verdiepingen import determine_bag_floors


@pytest.mark.parametrize(
    "areas,links,expected",
    [
        ([9345, 237, 160, 1057], ["p"] * 4, 3),
        ([4000, 4000], ["p", "p"], 2),
        ([4000, None], ["p", "p"], None),
        ([0], ["p"], None),
        ([float("inf")], ["p"], None),
        ([4000], ["p,q"], None),
        ([], [], None),
    ],
)
def test_floors_preserve_open_function_and_count_vbo_once(areas, links, expected):
    panden = gpd.GeoDataFrame(
        {"identificatie": ["p"], "gekozen_pandfunctie": [None]},
        geometry=[box(0, 0, 40, 100)],
        crs="EPSG:28992",
    )
    vbo = gpd.GeoDataFrame(
        {
            "identificatie": [str(i) for i in range(len(areas))],
            "pand_identificatie": links,
            "oppervlakte": areas,
            "gebruiksdoel": ["onderwijsfunctie,sportfunctie"] * len(areas),
        },
        geometry=[Point(1, 1)] * len(areas),
        crs=panden.crs,
    )
    original = vbo.copy()
    result = determine_bag_floors(panden, vbo)
    assert_geodataframe_equal(vbo, original)
    assert_geodataframe_equal(result[list(panden.columns)], panden)
    if expected is None:
        assert pd.isna(result.iloc[0]["berekend_aantal_bouwlagen"])
        assert result.iloc[0]["bouwlagen_status"] == "nog te beoordelen"
    else:
        assert result.iloc[0]["berekend_aantal_bouwlagen"] == expected
        assert result.iloc[0]["som_vbo_oppervlakte_m2"] == sum(areas)
    with pytest.raises(ValueError, match="EPSG:28992"):
        determine_bag_floors(panden.to_crs(4326), vbo)
