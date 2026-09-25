import geopandas as gpd
import pytest
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import Point, box

from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import prepare_bag


@pytest.mark.parametrize("empty", [False, True])
def test_bag_details_preserve_classification(tmp_path, empty):
    path = tmp_path / "bag.gpkg"
    panden = gpd.GeoDataFrame(
        {
            "identificatie": ["p1", "p2"],
            "status": ["Pand in gebruik", "Pand in gebruik"],
        },
        geometry=[box(0, 0, 10, 10), box(20, 0, 30, 10)],
        crs="EPSG:28992",
    )
    vbo = gpd.GeoDataFrame(
        {
            "identificatie": ["v1", "v2"],
            "pand_identificatie": ["p1", "p1"],
            "gebruiksdoel": ["woonfunctie", "winkelfunctie"],
            "oppervlakte": [150, 50],
        },
        geometry=[Point(2, 2), Point(3, 3)],
        crs=panden.crs,
    )
    panden.to_file(path, layer="pand", driver="GPKG")
    vbo.to_file(path, layer="verblijfsobject", driver="GPKG")
    bounds = (100, 100, 110, 110) if empty else (-1, -1, 31, 11)
    kwargs = {
        "pand_layer": "pand",
        "verblijfsobject_layer": "verblijfsobject",
        "bounds": bounds,
        "dike_area": box(-5, -5, 15, 15),
    }
    normal = prepare_bag(path, **kwargs)
    details = prepare_bag(path, include_details=True, **kwargs)
    assert_geodataframe_equal(normal, details[list(normal.columns)])
    assert "identificatie" in details.columns
    if empty:
        assert details.empty
        return

    pand = details.set_index("identificatie").loc["p1"]
    assert pand["gekozen_pandfunctie"] == "winkelfunctie"
    assert pand["som_vbo_oppervlakte_m2"] == 200
    assert pand["pandoppervlakte_m2"] == 100
    assert pand["berekend_aantal_bouwlagen"] == 2
    assert pand["code"] == 30
    assert pand["binnendijks"]
    other = details.set_index("identificatie").loc["p2"]
    assert not other["binnendijks"]
    assert other["code"] == 162
