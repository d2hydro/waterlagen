import geopandas as gpd
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import Point, box

from waterlagen.functioneel_landgebruik.bag_panden_en_verblijfsobjecten import (
    read_bag_source_data,
)


def test_source_keeps_multiple_goals_statuses_and_vbos_outside_bounds(tmp_path):
    path = tmp_path / "bag.gpkg"
    panden = gpd.GeoDataFrame(
        {
            "identificatie": ["12", "13", "14"],
            "status": ["Pand gesloopt", None, "Pand in gebruik"],
        },
        geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1), box(4, 0, 5, 1)],
        crs="EPSG:28992",
    )
    vbo = gpd.GeoDataFrame(
        {
            "identificatie": ["v1", "v2", "v3"],
            "pand_identificatie": ["12, 13", "112", "12"],
            "gebruiksdoel": ["onderwijsfunctie,sportfunctie", "winkelfunctie", None],
            "oppervlakte": [9345, 20, None],
            "status": ["Verblijfsobject ingetrokken"] * 3,
        },
        geometry=[Point(50, 50), Point(0.5, 0.5), Point(60, 60)],
        crs=panden.crs,
    )
    panden.to_file(path, layer="pand", driver="GPKG")
    vbo.to_file(path, layer="verblijfsobject", driver="GPKG")
    result = read_bag_source_data(path, bounds=(-1, -1, 6, 2))
    assert_geodataframe_equal(result.panden[list(panden.columns)], panden)
    actual = result.verblijfsobjecten.sort_values("identificatie").reset_index(
        drop=True
    )
    expected = vbo.iloc[[0, 2]].reset_index(drop=True)
    assert_geodataframe_equal(actual[list(vbo.columns)], expected)
    assert result.panden["bron_aantal_vbo"].tolist() == [2, 1, 0]
    summary = result.panden.set_index("identificatie").loc["12", "bron_vbo_overzicht"]
    assert "onderwijsfunctie,sportfunctie" in summary
    assert "9345" in summary
    assert "gehele verblijfsobject" in summary
    assert not {"hoofdfunctie", "code", "aantal_verdiepingen"} & set(
        result.panden.columns
    )
    empty = read_bag_source_data(path, bounds=(100, 100, 110, 110))
    assert empty.panden.empty and empty.verblijfsobjecten.empty
