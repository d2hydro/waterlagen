"""Produceer een DEM voor Nederland (standaard) of Alkmaar."""

import json
from dataclasses import asdict
from math import ceil
from pathlib import Path

import numpy as np
import rasterio
from shapely.geometry import box
from shapely.ops import unary_union
from tqdm.auto import tqdm

from waterlagen import _geopandas as wgpd
from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._production import production_run, validate_run_target
from waterlagen._sources import SourcePreparation, source_options
from waterlagen.administratieve_gebieden import (
    DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
    bestuurlijke_gebieden_path,
)
from waterlagen.ahn.productie import prepare_ahn
from waterlagen.areas import (
    Area,
    ProductionArea,
    area_name,
    ensure_land_boundary,
    resolve_area,
    resolve_workers,
)
from waterlagen.datastore import DataStore
from waterlagen.dem import DemConfig, bouw_dem_tiles
from waterlagen.dem.exports import validate_float_dem
from waterlagen.dem.inputs import resolve_landuse
from waterlagen.functioneel_landgebruik.gebouwen import building_paths
from waterlagen.functioneel_landgebruik.paths import source_path
from waterlagen.logger import get_logger
from waterlagen.settings import settings


def main(
    *,
    area: str | Area | ProductionArea = Area.nederland,
    landuse_run: Path | None = None,
    data_store: DataStore | None = None,
    output_root: Path | None = None,
    ahn_vrt: Path | None = None,
    workers: int | None = None,
    building_workers: int | None = None,
    config: DemConfig | None = None,
    run_id: str | None = None,
    resume: bool = False,
    overwrite: bool = False,
    refresh_sources: bool = False,
    offline: bool = False,
    preparation: SourcePreparation | None = None,
) -> Path:
    """Resolve suitable land use, prepare sources and produce an area DEM.

    Parameters
    ----------
    area : str or Area or ProductionArea
        Shared input selection; complete tile outputs are retained.
    landuse_run : pathlib.Path, optional
        Explicit completed land-use production. Otherwise discover or produce it.
    data_store : DataStore, optional
        Source caches and default production locations.
    output_root : pathlib.Path, optional
        Override the DEM output location for Python callers. The CLI instead
        configures the datastore for both DEM and dependent productions.
    ahn_vrt : pathlib.Path, optional
        Explicit AHN mosaic. Otherwise prepare the required cached AHN tiles.
    workers, building_workers : int, optional
        Override configured counts for tile and building processes.
    config : DemConfig, optional
        Interpolation and building elevation settings.
    run_id : str, optional
        Unique run name, default a UTC timestamp.
    resume, overwrite : bool
        Reuse or rebuild a compatible existing run.
    refresh_sources, offline : bool
        Refresh sources for a new run, or require locally available sources.
        Explicit source overrides are not refreshed.
    preparation : SourcePreparation, optional
        Shared source policy for nested productions.

    Returns
    -------
    pathlib.Path
        Validated DEM GeoTIFF. A Float32 companion is also produced.
    """
    store = data_store or DataStore()
    validate_run_target(
        output_root or store.processed_data_dir,
        "dem",
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
    config = config or DemConfig()
    workers = resolve_workers(workers, settings.dem_workers)
    building_workers = resolve_workers(building_workers, settings.dem_building_workers)
    with production_run(
        output_root or store.processed_data_dir,
        "dem",
        area.value,
        run_id=run_id,
        resume=resume,
        overwrite=overwrite,
        parameters={
            "workflow_version": 4,
            "area": area.identity,
            "config": json.loads(json.dumps(asdict(config))),
            "landuse_override": str(landuse_run.resolve()) if landuse_run else None,
            "ahn_override": str(ahn_vrt.resolve()) if ahn_vrt else None,
        },
    ) as run:
        logger = get_logger(__name__)
        dependency = resolve_landuse(
            store,
            run,
            area,
            config.building_max_search_distance_m,
            landuse_run,
            preparation=preparation,
        )
        paths = dependency.paths
        selected = dependency.tiles
        workers = min(workers, len(paths))
        run.metadata["workers"] = workers
        run.metadata["building_workers"] = min(building_workers, len(paths))
        run.metadata["tile_ids"] = selected.tile_id.tolist()
        run._save()
        logger.info(
            "DEM %s: %s tiles, %s workers; land use %s",
            area,
            len(paths),
            workers,
            dependency.path,
        )
        if not (run.path / "tiles.gpkg").exists():
            write_geopackage_layer_atomically(
                selected, run.path / "tiles.gpkg", layer_name="tiles"
            )
        inputs = {
            "tile_index": dependency.path / "tiles.gpkg",
            "mapping": dependency.path / "landgebruik_met_code.csv",
        }
        for number, path in enumerate(paths):
            inputs[f"landuse_{number}"] = path
            inputs[f"sources_{number}"] = source_path(path)
            inputs[f"ids_{number}"], inputs[f"buildings_{number}"] = building_paths(
                path
            )
        run.record_inputs(inputs)
        if ahn_vrt is None:
            # Keep a pinned VRT on resume; download_ahn validates/reuses its cache.
            ahn_vrt = run.path / "input" / "ahn.vrt"
            if not ahn_vrt.exists():
                margins = [
                    geometry.buffer(
                        config.interpolation_max_distance_m + dependency.resolution_m
                    )
                    for geometry in selected.geometry
                ]
                for path in paths:
                    buildings = wgpd.read_file(
                        building_paths(path)[1], layer="gebouwen"
                    )
                    if not buildings.empty:
                        margins.append(
                            box(*buildings.total_bounds).buffer(
                                config.building_max_search_distance_m
                                + dependency.resolution_m
                            )
                        )
                prepare_ahn(store, unary_union(margins), ahn_vrt, preparation)
        ensure_land_boundary(store, preparation)
        result = bouw_dem_tiles(
            run.path,
            ahn_vrt_path=ahn_vrt,
            landuse_tiles=paths,
            config=config,
            overwrite=overwrite,
            workers=workers,
            building_workers=building_workers,
            landgebied_path=bestuurlijke_gebieden_path(
                DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
                download_dir=store.administratieve_gebieden_dir,
            ),
        )
        validate_float_dem(result, run.path / "dem_float.tif")
        for name in ("dem", "dem_bron", "ahn_bron"):
            with (
                rasterio.open(run.path / f"{name}.vrt") as vrt,
                rasterio.open(run.path / f"{name}.tif") as cog,
            ):
                if (vrt.shape, vrt.transform, vrt.crs, vrt.scales, vrt.offsets) != (
                    cog.shape,
                    cog.transform,
                    cog.crs,
                    cog.scales,
                    cog.offsets,
                ):
                    raise ValueError(f"VRT/COG metadata wijkt af: {name}")
                block_height, block_width = cog.block_shapes[0]
                block_count = ceil(cog.height / block_height) * ceil(
                    cog.width / block_width
                )
                for _, window in tqdm(
                    cog.block_windows(1),
                    total=block_count,
                    desc=f"Controle {name}.vrt / {name}.tif",
                    unit="blok",
                ):
                    if not np.array_equal(
                        vrt.read(1, window=window),
                        cog.read(1, window=window),
                        equal_nan=True,
                    ):
                        raise ValueError(f"VRT/COG pixels wijken af: {name}")
        logger.info("DEM %s voltooid: identieke VRT/COG-pixels", area)
        return result
