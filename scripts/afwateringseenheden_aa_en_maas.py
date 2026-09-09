# %%
from waterlagen.administratieve_gebieden import (
    download_waterschapsgrenzen,
    normaliseer_waterschapsgrenzen,
    read_waterschapsgrenzen_layer,
)
from waterlagen.ahn import download_ahn
from waterlagen.hydamo import download_hydamo

WATERBEHEERCODE = "38"
BUFFER_M = 5000

# download administratieve grenzen van waterschappen
download = download_waterschapsgrenzen(overwrite=False)
raw = read_waterschapsgrenzen_layer(path=download.target_path)
waterschapsgrenzen = normaliseer_waterschapsgrenzen(raw)

administratief_gebied = waterschapsgrenzen.loc[
    waterschapsgrenzen["waterbeheercode"] == WATERBEHEERCODE, "geometry"
].make_valid()
if administratief_gebied.empty:
    raise ValueError(f"Geen waterschapsgrens gevonden voor code {WATERBEHEERCODE}")

# Download AHN DTM voor het beheergebied van Aa en Maas (en 5000m bij de buren)
dtm_mask = administratief_gebied.union_all().buffer(BUFFER_M)
dtm = download_ahn(poly_mask=dtm_mask, missing_only=True)

# Download HyDAMO
hydamo = download_hydamo(overwrite=False)
