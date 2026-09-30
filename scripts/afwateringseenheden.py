# %%
import argparse
import hashlib
import multiprocessing
import os
from collections.abc import Sequence
from pathlib import Path

from shapely.geometry.base import BaseGeometry

from waterlagen import datastore
from waterlagen._production import (
    ProductionRun,
    add_run_arguments,
    default_run_id,
    production_run,
    validate_run_options,
)
from waterlagen.administratieve_gebieden import (
    DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
    download_bestuurlijke_gebieden,
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
from waterlagen.settings import settings

WATERBEHEERCODE = "38"
BUFFER_M = 2000
BURN_DEPTH_M = 100
MAX_FILL_DEPTH_M = 50
TILE_SIZE_M = 10000
TILE_BUFFER_M = 2000
RANDOM_SEED = 12345
ENGINE = "pcraster"


def _waterbeheercode(value: str) -> str:
    code = value.strip()
    if not code.isascii() or not code.isdigit():
        raise argparse.ArgumentTypeError("Een waterbeheercode moet uit cijfers bestaan")
    return code


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Produceer afwateringseenheden per waterschap (standaard Aa en Maas).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--waterbeheercode",
        dest="waterbeheercodes",
        nargs="+",
        type=_waterbeheercode,
        default=[WATERBEHEERCODE],
        metavar="CODE",
        help="Een of meer codes, gescheiden door spaties; verwerking achter elkaar",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=settings.afwateringseenheden_workers,
        help="Maximaal aantal gelijktijdige rekenprocessen per waterschap",
    )
    add_run_arguments(parser)
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers moet een geheel getal van minstens 1 zijn")
    return args


def main(
    *,
    waterbeheercodes: Sequence[str] | None = None,
    workers: int | None = None,
    run_id: str | None = None,
    resume: bool = False,
    overwrite: bool = False,
) -> None:
    """Bereken de geselecteerde waterschappen achter elkaar, elk in een eigen map."""
    validate_run_options(run_id, resume=resume, overwrite=overwrite)
    run_id = run_id or default_run_id()
    if waterbeheercodes is None:
        waterbeheercodes = [WATERBEHEERCODE]
    codes = list(dict.fromkeys(_waterbeheercode(code) for code in waterbeheercodes))
    if not codes:
        raise ValueError("Geef minstens één waterbeheercode op")
    if workers is None:
        workers = settings.afwateringseenheden_workers
    if workers < 1:
        raise ValueError("Het aantal workers moet minstens 1 zijn")
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

    logger = init_logger(name="afwateringseenheden")
    # Controleer alle codes voordat een grote download of berekening begint.
    download = download_waterschapsgrenzen(overwrite=False)
    raw = read_waterschapsgrenzen_layer(path=download.target_path)
    waterschapsgrenzen = normaliseer_waterschapsgrenzen(raw)
    available_codes = set(waterschapsgrenzen["waterbeheercode"].dropna())
    unknown_codes = [code for code in codes if code not in available_codes]
    if unknown_codes:
        raise ValueError(
            f"Geen waterschapsgrens gevonden voor code(s): {', '.join(unknown_codes)}. "
            f"Beschikbare codes: {', '.join(sorted(available_codes))}"
        )

    logger.info("Waterschappen in deze productie: %s", ", ".join(codes))
    for code in codes:
        administratief_gebied = waterschapsgrenzen.loc[
            waterschapsgrenzen["waterbeheercode"] == code, "geometry"
        ].make_valid()
        spatial_mask = administratief_gebied.union_all().buffer(BUFFER_M)
        _produce_waterschap(
            code,
            spatial_mask,
            workers=workers,
            run_id=run_id,
            resume=resume,
            overwrite=overwrite,
            boundaries_path=download.target_path,
        )


def _produce_waterschap(
    waterbeheercode: str,
    spatial_mask: BaseGeometry,
    *,
    workers: int,
    run_id: str | None = None,
    resume: bool = False,
    overwrite: bool = False,
    boundaries_path: Path | None = None,
) -> None:
    """Produceer een waterschap in een nieuwe of expliciet hervatte run."""
    with production_run(
        datastore.processed_data_dir,
        "afwateringseenheden",
        f"waterschap_{waterbeheercode}",
        run_id=run_id,
        resume=resume,
        overwrite=overwrite,
        parameters={
            "crs": settings.crs,
            "waterbeheercode": waterbeheercode,
            "buffer_m": BUFFER_M,
            "burn_depth_m": BURN_DEPTH_M,
            "max_fill_depth_m": MAX_FILL_DEPTH_M,
            "tile_size_m": TILE_SIZE_M,
            "tile_buffer_m": TILE_BUFFER_M,
            "random_seed": RANDOM_SEED,
            "engine": ENGINE,
            "bestuurlijke_gebieden_year": DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
            "mask_sha256": hashlib.sha256(spatial_mask.wkb).hexdigest(),
        },
    ) as run:
        _produce(
            run,
            waterbeheercode,
            spatial_mask,
            workers=workers,
            overwrite=overwrite,
            boundaries_path=boundaries_path,
        )


def _produce(
    run: ProductionRun,
    waterbeheercode: str,
    spatial_mask: BaseGeometry,
    *,
    workers: int,
    overwrite: bool,
    boundaries_path: Path | None,
) -> None:
    run_dir = run.path
    logger = init_logger(
        name="afwateringseenheden",
        log_file=run_dir / "afwateringseenheden.log",
    )
    logger.info("Productie-uitvoermap voor waterschap %s: %s", waterbeheercode, run_dir)
    logger.info(
        "Instellingen: waterbeheercode=%s, buffer_m=%s, tile_size_m=%s, "
        "tile_buffer_m=%s, burn_depth_m=%s, max_fill_depth_m=%s, random_seed=%s, workers=%s",
        waterbeheercode,
        BUFFER_M,
        TILE_SIZE_M,
        TILE_BUFFER_M,
        BURN_DEPTH_M,
        MAX_FILL_DEPTH_M,
        RANDOM_SEED,
        workers,
    )

    dtm = download_ahn(poly_mask=spatial_mask, missing_only=True)

    # Vul AHN-tegels en rekenbuffers alleen binnen de Nederlandse landsgrens.
    bestuurlijke_gebieden = download_bestuurlijke_gebieden(
        year=DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
        overwrite=False,
    )

    # Selecteer het watersysteem opnieuw: de algemene cache kan een ander gebied zijn.
    hydamo = download_hydamo(overwrite=False)
    run.record_inputs(
        {
            "ahn": dtm,
            "hydamo": hydamo.target_path,
            "landsgrens": bestuurlijke_gebieden.target_path,
            "waterschapsgrenzen": boundaries_path,
        }
    )
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
        waterbeheercodes=[waterbeheercode],
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
        overwrite=overwrite,
    )

    # Bij het samenvoegen worden lijnrestjes verwijderd en lege delen aangevuld
    # vanuit bruikbare buurtegels.
    tile_result = calculate_afwateringseenheden_tiles(
        spatial_mask,
        burn_depth_m=BURN_DEPTH_M,
        ahn_vrt_path=dtm,
        landsgrens_path=bestuurlijke_gebieden.target_path,
        watersysteem_path=watersysteem_path,
        output_dir=run_dir / "tiles",
        merged_output_path=run_dir / "afwateringseenheden.gpkg",
        tile_size_m=TILE_SIZE_M,
        tile_buffer_m=TILE_BUFFER_M,
        max_fill_depth_m=MAX_FILL_DEPTH_M,
        engine=ENGINE,
        workers=workers,
        random_seed=RANDOM_SEED,
        overwrite=overwrite,
    )
    logger.info(
        "Waterschap %s klaar: %s tegels, %s overgeslagen, "
        "%s tegels met oorspronkelijke randproblemen; uitvoer: %s",
        waterbeheercode,
        len(tile_result.tile_results),
        len(tile_result.skipped_tile_ids),
        len(tile_result.boundary_issue_tile_ids),
        tile_result.merged_path,
    )


# Nodig op Windows: workers mogen de volledige workflow niet opnieuw starten.
if __name__ == "__main__":
    multiprocessing.freeze_support()
    main(**vars(_parse_args()))
