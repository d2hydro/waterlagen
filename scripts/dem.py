"""Produceer een DEM voor Nederland (standaard) of Alkmaar."""

import argparse
import json
from dataclasses import asdict
from math import ceil
from multiprocessing import freeze_support
from pathlib import Path

import numpy as np
import rasterio
from shapely.geometry import box
from shapely.ops import unary_union
from tqdm.auto import tqdm

from waterlagen import _geopandas as wgpd
from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._production import add_run_arguments, production_run
from waterlagen.administratieve_gebieden import (
    DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
    bestuurlijke_gebieden_path,
)
from waterlagen.ahn import AHNService, download_ahn, get_tiles_features
from waterlagen.areas import Area, resolve_workers
from waterlagen.datastore import DataStore
from waterlagen.dem import DemConfig, bouw_dem_tiles
from waterlagen.dem.exports import validate_float_dem
from waterlagen.dem.inputs import resolve_landuse
from waterlagen.functioneel_landgebruik.gebouwen import building_paths
from waterlagen.functioneel_landgebruik.paths import source_path
from waterlagen.logger import configure_logging, get_logger
from waterlagen.raster.vrt import create_vrt_file
from waterlagen.settings import settings


def main(
    *,
    area: Area = Area.nederland,
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
) -> Path:
    """Resolve area-specific land use, then produce or resume the DEM."""
    area = Area(area)
    store = data_store or DataStore()
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
            "workflow_version": 3,
            "config": json.loads(json.dumps(asdict(config))),
            "landuse_override": str(landuse_run.resolve()) if landuse_run else None,
            "ahn_override": str(ahn_vrt.resolve()) if ahn_vrt else None,
        },
    ) as run:
        configure_logging(log_file=run.path / "productie.log", stdout=True)
        logger = get_logger(__name__)
        try:
            dependency = resolve_landuse(
                store, run, area, config.building_max_search_distance_m, landuse_run
            )
        finally:
            # Prerequisite production has its own log file.
            configure_logging(log_file=run.path / "productie.log", stdout=True)
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
                indices = get_tiles_features(
                    ahn_service=AHNService(service="ahn_pdok"),
                    poly_mask=unary_union(margins),
                ).index.tolist()
                ahn_dir = download_ahn(
                    ahn_dir=store.ahn_dir,
                    select_indices=indices,
                    model="dtm",
                    cell_size="05",
                    missing_only=True,
                    create_vrt=False,
                )
                create_vrt_file(
                    ahn_vrt, files=[ahn_dir / f"{index}.tif" for index in indices]
                )
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


if __name__ == "__main__":
    freeze_support()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", type=Area, choices=list(Area), default=Area.nederland)
    parser.add_argument("--landuse-run", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--ahn-vrt", type=Path)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--building-workers", type=int)
    for parameter in (
        "building_initial_buffer_m",
        "building_buffer_step_m",
        "building_percentile",
        "building_max_search_distance_m",
        "interpolation_max_distance_m",
    ):
        parser.add_argument(
            "--" + parameter.replace("_", "-"),
            type=float,
            default=getattr(DemConfig(), parameter),
        )
    add_run_arguments(parser)
    arguments = vars(parser.parse_args())
    config_values = {
        name: arguments.pop(name)
        for name in DemConfig.__dataclass_fields__
        if name != "output"
    }
    main(**arguments, config=DemConfig(**config_values))
