# %%
from waterrasters import settings
from waterrasters.ahn import get_ahn_rasters

# %% [markdown]
#
# ## Download AHN. Je kunt de volgende settings aanpassen
# - `download_dir`: sub-dir van settings.source_data die je kunt overrulen SOURCE_DATA in een .env file
# - `ahn_type`: dtm_05, dsm_05, dtm_5 en dsm_5 werken volgens mij ook (niet getest)
# - `missings_only`: met True worden alleen missende tegels gedownload
# - `create_vrt`: hiermee wordt er een VRT-file bij geplaatst
# - `save_tiles_index`: met True wordt een GPKG met kaartindices geschreven
# - `save_int_16`: hiermee wordt de AHN gecomprimeert tot int16. Waarden worden opgeslagen in cm. Scheelt een hoop opslag.

get_ahn_rasters(
    download_dir=settings.ahn_dir,
    select_indices=["M_19BZ1", "M_25BN2", "M_14EN1", "M_14EZ1"],
    ahn_type="dtm_05m",
    missings_only=True,
    create_vrt=True,
    save_tiles_index=False,
    as_int_16=False,
)
