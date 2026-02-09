# %%

from waterlagen import datastore
from waterlagen.ahn import (
    AHNService,
    get_ahn_rasters,
    get_tiles_features,
    interpolate_ahn_tiles,
)
from waterlagen.bag.download import get_bag_features
from waterlagen.logger import init_logger

TILE_INDEX = "M_19BZ1"
MAX_SEARCH_DISTANCE = 250

############################
# AHN downloaden en bewerken
############################

logger = init_logger(
    name="ahn download", log_file=datastore.data_dir / "dem_processing.log", debug=False
)

# uitvogelen welke tiles je nodig hebt
tiles_gdf = get_tiles_features(ahn_service=AHNService(service="ahn_pdok"))
download_tiles = tiles_gdf[
    tiles_gdf.intersects(
        tiles_gdf.at[TILE_INDEX, "geometry"].buffer(MAX_SEARCH_DISTANCE)
    )
].index.to_list()


# tiles downloaden
ahn_vrt = get_ahn_rasters(missing_only=True, select_indices=download_tiles)

# interpoleren van dé tegel als dat nog niet is gedaan
ahn_interpolated_vrt = interpolate_ahn_tiles(
    ahn_vrt_file=ahn_vrt,
    indices=[TILE_INDEX],
    max_search_distance=MAX_SEARCH_DISTANCE,
    missing_only=True,
)

############################
# BAG downloaden en bewerken
############################

bag_pand_gdf = get_bag_features(
    bbox=tiles_gdf.at[TILE_INDEX, "geometry"].bounds, source="wfs", layer="pand"
)
bag_gpkg = datastore.bag_dir / "bag.gpkg"
bag_pand_gdf.to_file(bag_gpkg)
