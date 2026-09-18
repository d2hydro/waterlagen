"""Produce afwateringseenheden from the published AHN and HYDAMO sources."""

import math
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from waterlagen import datastore as default_datastore
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
from waterlagen.datastore import DataStore
from waterlagen.hydamo import download_hydamo
from waterlagen.logger import init_logger
from waterlagen.settings import settings


@dataclass(frozen=True)
class ProductionConfig:
    """Settings for the tiled production workflow.

    Parameters
    ----------
    waterbeheercode : str, optional
        Water authority code; ``"38"`` selects Aa en Maas.
    buffer_m : float, optional
        Buffer outside the authority boundary, in metres. Defaults to 2000.
    burn_depth_m : float, optional
        Secondary watercourse burn depth in metres. Defaults to 100.
    max_fill_depth_m : float, optional
        Maximum depression fill depth in metres. Defaults to 50.
    tile_size_m : float, optional
        Core tile size in metres. Defaults to 10000.
    tile_buffer_m : float, optional
        Calculation buffer per tile in metres. Defaults to 2000.
    workers : int or None, optional
        Number of processes. None uses settings.afwateringseenheden_workers.
    random_seed : int, optional
        PCRaster seed used for each tile. Defaults to 12345.
    """

    waterbeheercode: str = "38"
    buffer_m: float = 2000
    burn_depth_m: float = 100
    max_fill_depth_m: float = 50
    tile_size_m: float = 10000
    tile_buffer_m: float = 2000
    workers: int | None = None
    random_seed: int = 12345

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9]{1,4}", self.waterbeheercode) is None:
            raise ValueError("Waterbeheercode moet uit 1 tot 4 cijfers bestaan.")
        for name in ("buffer_m", "burn_depth_m", "max_fill_depth_m", "tile_buffer_m"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} moet een eindig getal van minimaal 0 zijn.")
        if not math.isfinite(self.tile_size_m) or self.tile_size_m <= 0:
            raise ValueError("tile_size_m moet een eindig getal groter dan 0 zijn.")
        if self.workers is not None and self.workers < 1:
            raise ValueError("workers moet minimaal 1 zijn.")
        if self.random_seed < 1:
            raise ValueError("random_seed moet minimaal 1 zijn.")


def produce_afwateringseenheden(
    config: ProductionConfig | None = None,
    *,
    data_store: DataStore | None = None,
) -> Path:
    """Produce one authority's afwateringseenheden in a new run directory.

    Parameters
    ----------
    config : ProductionConfig, optional
        Area and calculation settings. Defaults to the Aa en Maas workflow.
    data_store : DataStore, optional
        Storage for sources and results. Defaults to the package DataStore.

    Returns
    -------
    pathlib.Path
        Merged afwateringseenheden GeoPackage.

    Notes
    -----
    Valid source files are reused. Each invocation creates a new timestamped
    output directory and does not resume tiles from previous runs. PCRaster
    is checked before downloads start. CRS and raster settings follow the
    existing tiled calculation. Invoke from a guarded main entry point when
    using multiple processes.
    """
    config = config or ProductionConfig()
    data_store = data_store or default_datastore
    workers = config.workers
    if workers is None:
        workers = settings.afwateringseenheden_workers
    if workers < 1:
        raise ValueError("Het aantal processen moet minimaal 1 zijn.")
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
    area_name = f"waterschap_{config.waterbeheercode}"
    if config.waterbeheercode == "38":
        area_name = "aa_en_maas"
    run_dir = data_store.afwateringseenheden_path / f"{area_name}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    logger = init_logger(
        name="afwateringseenheden",
        log_file=run_dir / "afwateringseenheden.log",
    )
    logger.info(
        "Nieuwe uitvoermap voor waterschap %s: %s", config.waterbeheercode, run_dir
    )
    logger.info(
        "Brongegevens: %s; instellingen: %s; processen: %s",
        data_store.source_data_dir,
        config,
        workers,
    )

    # Bestaande waterschapsgrenzen hergebruiken, of eenmalig downloaden.
    download = download_waterschapsgrenzen(
        download_dir=data_store.administratieve_gebieden_dir, overwrite=False
    )
    raw = read_waterschapsgrenzen_layer(path=download.target_path)
    waterschapsgrenzen = normaliseer_waterschapsgrenzen(raw)
    administratief_gebied = waterschapsgrenzen.loc[
        waterschapsgrenzen["waterbeheercode"] == config.waterbeheercode, "geometry"
    ].make_valid()
    if administratief_gebied.empty:
        raise ValueError(
            f"Geen waterschapsgrens gevonden voor code {config.waterbeheercode}"
        )

    spatial_mask = administratief_gebied.union_all().buffer(config.buffer_m)
    dtm = download_ahn(
        ahn_dir=data_store.ahn_dir, poly_mask=spatial_mask, missing_only=True
    )

    # Vul AHN-tegels en rekenbuffers alleen binnen de Nederlandse landsgrens.
    bestuurlijke_gebieden = download_bestuurlijke_gebieden(
        year=DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
        download_dir=data_store.administratieve_gebieden_dir,
        overwrite=False,
    )

    # Selecteer het watersysteem opnieuw: de algemene cache kan een ander gebied zijn.
    hydamo = download_hydamo(download_dir=data_store.hydamo_dir, overwrite=False)
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
        waterbeheercodes=[config.waterbeheercode],
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

    # Bij het samenvoegen worden lijnrestjes verwijderd en lege delen aangevuld
    # vanuit bruikbare buurtegels.
    tile_result = calculate_afwateringseenheden_tiles(
        spatial_mask,
        burn_depth_m=config.burn_depth_m,
        ahn_vrt_path=dtm,
        landsgrens_path=bestuurlijke_gebieden.target_path,
        watersysteem_path=watersysteem_path,
        output_dir=run_dir / "tiles",
        merged_output_path=run_dir / "afwateringseenheden.gpkg",
        tile_size_m=config.tile_size_m,
        tile_buffer_m=config.tile_buffer_m,
        max_fill_depth_m=config.max_fill_depth_m,
        engine="pcraster",
        workers=workers,
        random_seed=config.random_seed,
        data_store=data_store,
        overwrite=False,
    )
    logger.info(
        "Waterschap %s klaar: %s tegels, %s overgeslagen, "
        "%s tegels met oorspronkelijke randproblemen; uitvoer: %s",
        config.waterbeheercode,
        len(tile_result.tile_results),
        len(tile_result.skipped_tile_ids),
        len(tile_result.boundary_issue_tile_ids),
        tile_result.merged_path,
    )
    if tile_result.merged_path is None:
        raise RuntimeError(
            "Geen samengevoegde afwateringseenheden geproduceerd; controleer het logbestand."
        )
    return tile_result.merged_path
