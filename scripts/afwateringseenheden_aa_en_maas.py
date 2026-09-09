# %%
from shapely.geometry import box

from waterlagen import datastore
from waterlagen.administratieve_gebieden import (
    download_waterschapsgrenzen,
    normaliseer_waterschapsgrenzen,
    read_waterschapsgrenzen_layer,
)
from waterlagen.afwateringseenheden import (
    calculate_subcatchments,
    prepare_watersysteem,
    prepare_watersysteem_rasters,
    read_hydroobjecten,
    read_puntobjecten,
    write_watersysteem,
)
from waterlagen.afwateringseenheden.objects import CATEGORIE_OPPERVLAKTEWATER_COLUMN
from waterlagen.afwateringseenheden.pcraster import require_pcraster
from waterlagen.ahn import download_ahn
from waterlagen.hydamo import download_hydamo
from waterlagen.logger import init_logger

logger = init_logger(
    name="afwateringseenheden",
    log_file=datastore.data_dir / "afwateringseenheden.log",
)

WATERBEHEERCODE = "38"
BUFFER_M = 5000
BURN_DEPTH_M = 100
# Dit vierkant ligt binnen de AHN-VRT en bevat hydroobject_segmenten.
RUIMTELIJK_VIERKANT = box(155_000, 415_000, 160_000, 420_000)
ENGINE = "pcraster"

# if PCRaster is used as engine, we should run an environment that has it
if ENGINE == "pcraster":
    require_pcraster()

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

# Maak voor een expliciet vierkant de twee rasterinvoerlagen voor de
# vervolgberekening. De AHN-aanroep hierboven levert de gebruikte dtm_05.vrt.
rasters = prepare_watersysteem_rasters(
    RUIMTELIJK_VIERKANT,
    burn_depth_m=BURN_DEPTH_M,
    ahn_vrt_path=dtm,
    watersysteem_path=watersysteem_path,
    output_dir=datastore.afwateringseenheden_path / "190000_375000",
    overwrite=True,
)
logger.info(
    "Prepared Aa en Maas rasters: DEM %s and hydroobject segments %s",
    rasters.dem_path,
    rasters.hydroobject_segment_path,
)
subcatchments = calculate_subcatchments(
    rasters, watersysteem_path=watersysteem_path, engine=ENGINE
)
logger.info(
    "Prepared Aa en Maas subcatchments at %s",
    subcatchments.subcatchments_path,
)
