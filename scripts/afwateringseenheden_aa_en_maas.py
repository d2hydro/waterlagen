# %%
from waterlagen import datastore
from waterlagen.administratieve_gebieden import (
    download_waterschapsgrenzen,
    normaliseer_waterschapsgrenzen,
    read_waterschapsgrenzen_layer,
)
from waterlagen.afwateringseenheden import (
    prepare_watersysteem,
    read_hydroobjecten,
    read_puntobjecten,
    write_watersysteem,
)
from waterlagen.afwateringseenheden.objects import CATEGORIE_OPPERVLAKTEWATER_COLUMN
from waterlagen.ahn import download_ahn
from waterlagen.hydamo import download_hydamo
from waterlagen.logger import init_logger

logger = init_logger(
    name="afwateringseenheden",
    log_file=datastore.data_dir / "afwateringseenheden.log",
)

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
spatial_mask = administratief_gebied.union_all().buffer(BUFFER_M)
dtm = download_ahn(poly_mask=spatial_mask, missing_only=True)

# Download HyDAMO
hydamo = download_hydamo(overwrite=False)

# Lees, prepareer en schrijf het HyDAMO-watersysteem voor vervolgstappen.
hydroobjecten = read_hydroobjecten(
    hydamo.target_path,
    spatial_selection=spatial_mask,
    waterbeheercodes=[WATERBEHEERCODE],
)
hydroobject_primair = hydroobjecten.loc[
    hydroobjecten[CATEGORIE_OPPERVLAKTEWATER_COLUMN] == "primair"
].copy()
hydroobject_secundair = hydroobjecten.loc[
    hydroobjecten[CATEGORIE_OPPERVLAKTEWATER_COLUMN] == "secundair"
].copy()
puntobjecten = read_puntobjecten(
    hydamo.target_path,
    layers=["gemaal", "stuw"],
    spatial_selection=spatial_mask,
    waterbeheercodes=[WATERBEHEERCODE],
)
watersysteem = prepare_watersysteem(
    hydroobject_primair,
    puntobjecten,
    hydroobject_secundair=hydroobject_secundair,
)
watersysteem_path = write_watersysteem(
    hydroobject_primair=hydroobject_primair,
    hydroobject_secundair=hydroobject_secundair,
    watersysteem=watersysteem,
    overwrite=True,
)
logger.info("Prepared Aa en Maas watersysteem at %s", watersysteem_path)
