# %%

from waterlagen.bag import get_bag_features_from_wfs


def test_download_bag_pand():
    """test BAG pand feature download"""

    """download some data"""
    gdf = get_bag_features_from_wfs(
        type_name="bag:pand",
        bbox=(111900, 515300, 114300, 517300),
    )
    assert not gdf.empty

    # assert if pand only contains polygons
    assert list(gdf.geom_type.unique()) == ["Polygon"]

    # assert if id starts with pand
    assert gdf.id.str.startswith("pand").all()


def test_download_bag_verblijfsobject():
    """test BAG verblijfsobject feature download"""

    """download some data"""
    gdf = get_bag_features_from_wfs(
        type_name="bag:verblijfsobject",
        bbox=(111900, 515300, 114300, 517300),
    )
    assert not gdf.empty

    # assert if pand only contains points
    assert list(gdf.geom_type.unique()) == ["Point"]

    # assert if id starts with pand
    assert gdf.id.str.startswith("verblijfsobject").all()
