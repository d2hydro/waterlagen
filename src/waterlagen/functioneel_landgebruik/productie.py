"""Landelijke productie in een nieuwe of expliciet hervatte uitvoermap."""

import hashlib
import json
import shutil
from datetime import datetime
from math import isfinite
from pathlib import Path

import pyogrio
from osgeo import gdal

from waterlagen._filesystem import replace_file
from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._production import ProductionRun, production_run, validate_run_target
from waterlagen._sources import SourcePreparation, source_options
from waterlagen.areas import (
    Area,
    ProductionArea,
    area_name,
    ensure_land_boundary,
    resolve_area,
    resolve_workers,
    select_area_tiles,
)
from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik import (
    bouw_functioneel_landgebruik_tiles,
)
from waterlagen.functioneel_landgebruik.aanvullen import DONOR_ALLOWED, SOURCE_LAYERS
from waterlagen.functioneel_landgebruik.landgebruikstabel import (
    DEFAULT_MAPPING_CSV,
    LanduseTable,
    load_landuse_table,
)
from waterlagen.functioneel_landgebruik.legenda import (
    create_landuse_cog,
    write_qgis_style,
)
from waterlagen.functioneel_landgebruik.paths import building_paths, source_path
from waterlagen.functioneel_landgebruik.sources import prepare_sources
from waterlagen.logger import get_logger
from waterlagen.raster.tiles import build_tiles, read_tiles
from waterlagen.raster.vrt import create_cog_file, create_vrt_file
from waterlagen.settings import settings

# Instellingen voor landelijke productie.
RESOLUTION_M = 0.5
GAP_FILL_DISTANCE_M = 1.0
TEGELGROOTTE_M = 5000
BGT_BESTAND = "bgt.gpkg"
LANDGEBRUIK_CSV = DEFAULT_MAPPING_CSV
CONTROLE_OPSLAAN = True  # Alleen NoData-vlakken met bron en reden.
# Bestaande bronbestanden en het tegelrooster worden hergebruikt.


def main(
    data_store: DataStore | None = None,
    *,
    area: str | Area | ProductionArea = Area.nederland,
    workers: int | None = None,
    building_context_m: float = 5.0,
    mapping_csv: Path | None = None,
    bgt_path: Path | None = None,
    run_id: str | None = None,
    resume: bool = False,
    overwrite: bool = False,
    refresh_sources: bool = False,
    offline: bool = False,
    preparation: SourcePreparation | None = None,
) -> Path:
    """Produce functional land use with building companions for an area.

    Parameters
    ----------
    data_store : DataStore, optional
        Configured source and processed-data locations.
    area : Area
        Named input area or water authority code; complete intersecting tiles are retained.
    workers : int, optional
        Override settings.functioneel_landgebruik_workers; may change on resume.
    building_context_m : float
        Prepared neighbour distance needed for subsequent building sampling.
    mapping_csv, bgt_path : pathlib.Path, optional
        Classification table and prepared BGT override. Other sources use the datastore.
    run_id : str, optional
        Output run name, default a UTC timestamp.
    resume, overwrite : bool
        Explicitly reuse or rebuild a compatible run. Existing inputs are checked.

    refresh_sources, offline : bool
        Refresh sources for a new run, or require local inputs without downloads.
    preparation : SourcePreparation, optional
        Shared source policy for nested productions.

    Returns
    -------
    pathlib.Path
        The functional-land-use COG in the area-specific production folder.
    """
    if not isfinite(building_context_m) or building_context_m < 0:
        raise ValueError("building_context_m must be finite and non-negative")
    workers = resolve_workers(workers, settings.functioneel_landgebruik_workers)
    store = data_store or DataStore()
    validate_run_target(
        store.processed_data_dir,
        "functioneel_landgebruik",
        area_name(area),
        run_id,
        resume=resume,
        overwrite=overwrite,
    )
    preparation = source_options(
        preparation,
        refresh_sources=refresh_sources,
        offline=offline,
        resume=resume,
        overwrite=overwrite,
    )
    area = resolve_area(area, store, preparation)
    mapping_csv = Path(mapping_csv or LANDGEBRUIK_CSV)
    table = load_landuse_table(mapping_csv)
    context_parameters = {"building_context_m": building_context_m}
    with production_run(
        store.processed_data_dir,
        "functioneel_landgebruik",
        area.value,
        run_id=run_id,
        resume=resume,
        overwrite=overwrite,
        parameters={
            "area": area.identity,
            "building_ids": True,
            "tile_layout_version": 2,
            **context_parameters,
            "crs": settings.crs,
            "resolution_m": RESOLUTION_M,
            "gap_fill_distance_m": GAP_FILL_DISTANCE_M,
            "tile_size_m": TEGELGROOTTE_M,
            "diagnostics": CONTROLE_OPSLAAN,
            "csv_sha256": hashlib.sha256(mapping_csv.read_bytes()).hexdigest(),
        },
    ) as run:
        return _produce(
            store,
            run,
            mapping_csv=mapping_csv,
            table=table,
            bgt_path=bgt_path,
            overwrite=overwrite,
            area=area,
            workers=workers,
            building_context_m=building_context_m,
            preparation=preparation,
        )


def _produce(
    store: DataStore,
    run: ProductionRun,
    *,
    mapping_csv: Path,
    table: LanduseTable,
    bgt_path: Path | None,
    overwrite: bool,
    area: str | Area | ProductionArea,
    workers: int,
    building_context_m: float,
    preparation: SourcePreparation,
) -> Path:
    if int(gdal.VersionInfo()) < 3120000:
        raise RuntimeError("Embedded raster attribute tables require GDAL >= 3.12")
    output = run.path
    logger = get_logger(__name__)
    logger.info("Productie-uitvoermap: %s", output)
    csv_path = output / "landgebruik_met_code.csv"
    if csv_path.exists() and csv_path.read_bytes() != mapping_csv.read_bytes():
        raise ValueError(
            f"Runfolder '{output.resolve()}' bevat een andere landgebruik-CSV "
            f"dan het opgegeven bestand '{mapping_csv.resolve()}'. "
            f"Verwijder '{csv_path.resolve()}' om de nieuwe CSV te gebruiken, "
            "of kies een nieuwe uitvoermap met --run-id NAAM. "
            "Gebruik --overwrite om de uitvoer van een compatibele run opnieuw te maken."
        )
    if mapping_csv.resolve() != csv_path.resolve() and not csv_path.exists():
        shutil.copyfile(mapping_csv, csv_path)
    status = {
        "started": datetime.now().astimezone().isoformat(),
        "output": str(output),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "resolution_m": RESOLUTION_M,
        "gap_fill_distance_m": GAP_FILL_DISTANCE_M,
        "workers": workers,
        "rwzi": "nog te bepalen uit bronconfiguratie",
        "drinkwater": "nog te bepalen uit bronconfiguratie",
    }

    def stage(name: str) -> None:
        status["stage"] = name
        status["updated"] = datetime.now().astimezone().isoformat()
        temporary = output / "status.tmp.json"
        temporary.write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        replace_file(temporary, output / "status.json")
        logger.info("%s", name)

    try:
        sources = prepare_sources(
            store, preparation, bgt_path=bgt_path, workers=workers
        )
        bgt = sources.bgt_gpkg
        featuretypes = [
            "waterdeel",
            "wegdeel",
            "ondersteunendwaterdeel",
            "ondersteunendwegdeel",
            "begroeidterreindeel",
            "onbegroeidterreindeel",
        ]
        stage("Voorbereide actuele BGT gebruiken, inclusief aanvullende controlelagen")
        if not bgt.is_file():
            raise FileNotFoundError(
                f"BGT-bestand ontbreekt: {bgt}. "
                "Bronvoorbereiding heeft geen BGT opgeleverd."
            )
        for name in featuretypes:
            columns = set(pyogrio.read_info(bgt, layer="bgt_" + name)["fields"])
            if not {"bgt-status", "eindRegistratie", "objectEindTijd"}.issubset(
                columns
            ):
                raise ValueError("Einddatumvelden ontbreken in " + name)
        status["rwzi"] = (
            str(sources.rwzi_gpkg)
            if sources.rwzi_gpkg is not None
            else "niet uitgevoerd: terreinbron ontbreekt"
        )
        status["drinkwater"] = (
            str(sources.drinking_water_gpkg)
            if sources.drinking_water_gpkg is not None
            else "niet uitgevoerd: terreinbron ontbreekt"
        )
        status["sources"] = {
            name: str(path) if path else None for name, path in vars(sources).items()
        }
        run.record_inputs(vars(sources))
        stage("Landelijk tegelrooster maken")
        tiles = build_tiles(
            target_path=output / "grid.gpkg",
            boundary_path=ensure_land_boundary(store, preparation),
            tile_size_m=TEGELGROOTTE_M,
            overwrite=overwrite,
        )
        selected = select_area_tiles(read_tiles(tiles), area)
        tiles = output / "tiles.gpkg"
        if not tiles.exists() or overwrite:
            write_geopackage_layer_atomically(selected, tiles, layer_name="tiles")
        workers = min(workers, len(selected))
        status["workers"] = workers
        run.metadata["workers"] = workers
        run._save()
        status["tile_count"] = int(pyogrio.read_info(tiles, layer="tiles")["features"])
        stage(f"Rastertegels berekenen voor {area.value}")
        result = bouw_functioneel_landgebruik_tiles(
            write_building_ids=True,
            building_context_m=building_context_m,
            target_dir=output / "tiles",
            tiles_path=tiles,
            workers=workers,
            resolution_m=RESOLUTION_M,
            gap_fill_distance_m=GAP_FILL_DISTANCE_M,
            sources=sources,
            download_missing_sources=False,
            overwrite=overwrite,
            mapping_csv=csv_path,
            diagnostics_path=output / "nodata.gpkg" if CONTROLE_OPSLAAN else None,
        )
        status["completed_tiles"] = len(result)
        stage("VRT samenstellen")
        vrt = create_vrt_file(
            vrt_file=output / "functioneel_landgebruik.vrt", files=result
        )
        stage(f"GeoTIFF maken voor {area.value}")
        tif = output / "functioneel_landgebruik.tif"
        style = write_qgis_style(tif, table)
        create_landuse_cog(vrt, tif, style, overwrite=overwrite)
        stage("Bronnenraster samenstellen")
        sources_vrt = create_vrt_file(
            vrt_file=output / "functioneel_landgebruik_bronnen.vrt",
            files=[source_path(path) for path in result],
        )
        sources_tif = create_cog_file(
            vrt_file=sources_vrt,
            cog_file=output / "functioneel_landgebruik_bronnen.tif",
            overwrite=overwrite,
        )
        (output / "functioneel_landgebruik_bronnen.json").write_text(
            json.dumps(
                {
                    code: {"source_layer": label, "donor_allowed": DONOR_ALLOWED[code]}
                    for code, label in SOURCE_LAYERS.items()
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        status["sources_raster"] = str(sources_tif)
        create_vrt_file(
            vrt_file=output / "functioneel_landgebruik_gebouw_ids.vrt",
            files=[building_paths(path)[0] for path in result],
        )
        status["result"] = str(tif)
        stage("Voltooid")
        return tif
    except Exception as error:
        status["error"] = repr(error)
        stage("Mislukt")
        raise
