# %%
import multiprocessing
import os
from datetime import UTC, datetime

from waterlagen import datastore
from waterlagen.administratieve_gebieden import (
    download_waterschapsgrenzen,
    normaliseer_waterschapsgrenzen,
    read_waterschapsgrenzen_layer,
)
from waterlagen.afwateringseenheden import (
    calculate_afwateringseenheden_tiles,
    prepare_watersysteem,
    read_hydroobjecten,
    read_puntobjecten,
    write_watersysteem,
)
from waterlagen.afwateringseenheden.objects import CATEGORIE_OPPERVLAKTEWATER_COLUMN
from waterlagen.afwateringseenheden.pcraster import require_pcraster
from waterlagen.ahn import download_ahn
from waterlagen.hydamo import download_hydamo
from waterlagen.logger import init_logger

WATERBEHEERCODE = "38"
BUFFER_M = 5000
BURN_DEPTH_M = 100
MAX_FILL_DEPTH_M = 50
TILE_SIZE_M = 10000
TILE_BUFFER_M = 2000
WORKERS = 7
RANDOM_SEED = 12345
ENGINE = "pcraster"


def main() -> None:
    """Bereken heel Aa en Maas parallel in een nieuwe uitvoermap."""
    require_pcraster()

    # De instellingen worden door de nieuwe workerprocessen overgenomen.
    for name in (
        "GDAL_NUM_THREADS",
        "VRT_NUM_THREADS",
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
    ):
        os.environ[name] = "1"

    timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = datastore.afwateringseenheden_path / f"aa_en_maas_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    logger = init_logger(
        name="afwateringseenheden",
        log_file=run_dir / "afwateringseenheden.log",
    )
    logger.info("Nieuwe Aa en Maas uitvoermap: %s", run_dir)

    # Bestaande waterschapsgrenzen hergebruiken, of eenmalig downloaden.
    download = download_waterschapsgrenzen(overwrite=False)
    raw = read_waterschapsgrenzen_layer(path=download.target_path)
    waterschapsgrenzen = normaliseer_waterschapsgrenzen(raw)
    administratief_gebied = waterschapsgrenzen.loc[
        waterschapsgrenzen["waterbeheercode"] == WATERBEHEERCODE, "geometry"
    ].make_valid()
    if administratief_gebied.empty:
        raise ValueError(f"Geen waterschapsgrens gevonden voor code {WATERBEHEERCODE}")

    # Zoals oorspronkelijk: beheergebied plus 5 km bij de buren.
    spatial_mask = administratief_gebied.union_all().buffer(BUFFER_M)
    dtm = datastore.ahn_dir / "dtm_05" / "dtm_05.vrt"
    if dtm.is_file():
        logger.info("Hergebruik bestaande AHN VRT: %s", dtm)
    else:
        dtm = download_ahn(poly_mask=spatial_mask, missing_only=True)

    watersysteem_path = datastore.afwateringseenheden_path / "watersysteem.gpkg"
    if watersysteem_path.is_file():
        logger.info("Hergebruik bestaand watersysteem: %s", watersysteem_path)
    else:
        # Alleen als er nog geen watersysteem is: voorbereiden in deze runmap.
        hydamo = download_hydamo(overwrite=False)
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
            output_path=run_dir / "watersysteem.gpkg",
            overwrite=False,
        )

    # Alle tegels, vaste 5 km buffer, geen extra pogingen met grotere buffers.
    # Bij het samenvoegen worden lijnrestjes verwijderd en lege delen aangevuld
    # vanuit bruikbare buurtegels.
    tile_result = calculate_afwateringseenheden_tiles(
        spatial_mask,
        burn_depth_m=BURN_DEPTH_M,
        ahn_vrt_path=dtm,
        watersysteem_path=watersysteem_path,
        output_dir=run_dir / "tiles",
        merged_output_path=run_dir / "afwateringseenheden.gpkg",
        tile_size_m=TILE_SIZE_M,
        tile_buffer_m=TILE_BUFFER_M,
        retry_tile_buffer_m=(),
        max_fill_depth_m=MAX_FILL_DEPTH_M,
        engine=ENGINE,
        workers=WORKERS,
        random_seed=RANDOM_SEED,
        overwrite=False,
    )
    logger.info(
        "Aa en Maas klaar: %s tegels, %s overgeslagen, "
        "%s tegels met oorspronkelijke randproblemen; uitvoer: %s",
        len(tile_result.tile_results),
        len(tile_result.skipped_tile_ids),
        len(tile_result.boundary_issue_tile_ids),
        tile_result.merged_path,
    )


# Nodig op Windows: workers mogen de volledige workflow niet opnieuw starten.
if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
