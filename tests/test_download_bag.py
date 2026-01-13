# %%
import geopandas as gpd

from waterrasters.bag import get_bag_features


def test_download_bgt(bag_dir):
    """test if BGT-downloader works."""

    """download some data"""
    download_dir = get_bag_features(
        typenames=["bag:verblijfsobject", "bag:pand"],
        bbox=(111900, 515300, 114300, 517300),
        download_dir=bag_dir,
    )
    assert download_dir.exists()

    # assert if pand exists and is not empty
    pand_gpkg = download_dir / "bag_pand.gpkg"
    assert pand_gpkg.exists()
    gdf = gpd.read_file(pand_gpkg)
    assert not gdf.empty

    # assert if pand only contains polygons
    assert list(gdf.geom_type.unique()) == ["Polygon"]

    # assert if pand exists and is not empty
    verblijfsobject_gpkg = download_dir / "bag_verblijfsobject.gpkg"
    assert verblijfsobject_gpkg.exists()
    gdf = gpd.read_file(verblijfsobject_gpkg)
    assert not gdf.empty

    # assert if pand only contains polygons
    assert list(gdf.geom_type.unique()) == ["Point"]
