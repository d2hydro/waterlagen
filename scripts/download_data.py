# %%
from waterrasters import settings
from waterrasters.ahn import create_download_dir, get_ahn_rasters, get_tiles_gdf
from waterrasters.ahn_api_config import AHNService
from waterrasters.bag import download_bag_light, get_bag_panden
from waterrasters.bgt import get_bgt_features

# %% [markdown]
#
# ## Download AHN. Je kunt de volgende settings aanpassen
# - `download_dir`: sub-dir van settings.source_data die je kunt overrulen SOURCE_DATA in een .env file
# - `select_indices`: kaartbladen die je wilt selecteren
# - `model`: dtm of dsm
# - `ahn_version`: 3 t/m 6
# - `service`: ahn_pdok (https://service.pdok.nl/rws/ahn/atom/index.xml) of ahn_datastroom (https://www.ahn.nl)
# - `missing_only`: met True worden alleen missende tegels gedownload
# - `create_vrt`: hiermee wordt er een VRT-file bij geplaatst
# - `save_tiles_index`: met True wordt een GPKG met kaartindices geschreven

cell_size = "05"
model = "dtm"
ahn_version = 5
ahn_indices = ["M_19BZ1"]


download_dir = create_download_dir(
    root_dir=settings.ahn_dir,
    model=model,
    cell_size=cell_size,
    ahn_version=ahn_version,
)

get_ahn_rasters(
    download_dir=download_dir,
    select_indices=ahn_indices,
    model=model,
    service="ahn_datastroom",
    ahn_version=ahn_version,
    cell_size=cell_size,
    missing_only=False,
    create_vrt=True,
    save_tiles_index=True,
)


# %% [markdown]
#
# ## Download BGT
# Specificeer (BGT) `featuretypes`. Deze worden weggeschreven naar GeoPackages in download_dir
# We gebruiken hier de extent van de gedownloade AHN-tegel(s) als mask

poly_mask = get_tiles_gdf(
    ahn_service=AHNService(service="ahn_datastroom"), select_indices=ahn_indices
).union_all()
bgt_dir = get_bgt_features(
    featuretypes=["waterdeel", "wegdeel", "pand"],
    poly_mask=poly_mask,
    download_dir=settings.bgt_dir,
)

# %% [markdown]
#
# ## Download BAG
# Specificeer bounding-box op basis van poly_mask

bag_gpkg = get_bag_panden(download_dir=settings.bag_dir)
bag_light_gpkg = download_bag_light(bag_dir=settings.bag_dir)
