# %%
import geopandas as gpd
from shapely.geometry import box

from waterrasters.bgt import get_bgt_features

POLY_MASK = box(111900, 515300, 114300, 517300)


def test_download_bgt(bgt_dir):
    """test if BGT-downloader works."""

    """download some data"""
    download_dir = get_bgt_features(
        featuretypes=["waterdeel", "pand"],
        poly_mask=POLY_MASK,
        download_dir=bgt_dir,
    )
    assert download_dir.exists()

    # assert if waterdeel exists and is not empty
    waterdeel_gpkg = download_dir / "bgt_waterdeel.gpkg"
    assert waterdeel_gpkg.exists()
    gdf = gpd.read_file(waterdeel_gpkg)
    assert not gdf.empty

    # assert if waterdeel only contains polygons
    assert list(gdf.geom_type.unique()) == ["Polygon"]

    # assert if pand exists and is not empty
    pand_gpkg = download_dir / "bgt_pand.gpkg"
    assert pand_gpkg.exists()
    gdf = gpd.read_file(pand_gpkg)
    assert not gdf.empty

    # assert if pand only contains polygons
    assert list(gdf.geom_type.unique()) == ["Point", "MultiPolygon"]
