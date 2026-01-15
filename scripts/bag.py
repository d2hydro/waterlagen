from waterlagen import datastore
from waterlagen.ahn import get_tiles_features
from waterlagen.ahn.api_config import AHNService
from waterlagen.bag import download_bag_nl

# download BAG in DataStore
bag_gpkg = download_bag_nl(download_dir=datastore.bag_dir, overwrite=False)

# or download bag for specific extent
ahn_indices = ["M_19BZ1"]
ahn_service = AHNService(service="ahn_pdok")
tiles_gdf = get_tiles_features(service=ahn_service, selected_indices=ahn_indices)
