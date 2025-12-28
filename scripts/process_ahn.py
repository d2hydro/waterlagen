# %%
from waterrasters import settings
from waterrasters.ahn import create_download_dir, get_ahn_rasters

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

download_dir = create_download_dir(
    root_dir=settings.ahn_dir,
    model=model,
    cell_size=cell_size,
    ahn_version=ahn_version,
)

get_ahn_rasters(
    download_dir=download_dir,
    select_indices=["M_19BZ1"],
    model=model,
    service="ahn_datastroom",
    ahn_version=ahn_version,
    cell_size=cell_size,
    missing_only=False,
    create_vrt=True,
    save_tiles_index=True,
)
