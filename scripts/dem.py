"""Produceer een DEM voor Nederland (standaard) of Alkmaar."""

import argparse
import json
from dataclasses import asdict
from multiprocessing import freeze_support
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import box
from shapely.ops import unary_union

from waterlagen import _geopandas as wgpd
from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._production import add_run_arguments, production_run
from waterlagen.ahn import AHNService, download_ahn, get_tiles_features
from waterlagen.areas import Area, resolve_workers, select_area_tiles
from waterlagen.datastore import DataStore
from waterlagen.dem import DemConfig, bouw_dem_tiles
from waterlagen.dem.inputs import resolve_landuse
from waterlagen.functioneel_landgebruik import (
    FunctioneelLandgebruikSources,
    bouw_functioneel_landgebruik_tiles,
)
from waterlagen.functioneel_landgebruik.gebouwen import building_paths
from waterlagen.logger import configure_logging, get_logger
from waterlagen.raster.tiles import read_tiles, tile_filename, tile_from_row
from waterlagen.raster.vrt import create_vrt_file
from waterlagen.settings import settings


def select_alkmaar_tiles(tiles: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Backward-compatible selector using the shared production area."""
    return select_area_tiles(tiles, Area.alkmaar)


def _legacy_main(
    *,
    landuse_run: Path,
    data_store: DataStore | None = None,
    output_root: Path | None = None,
    ahn_vrt: Path | None = None,
    prepare_landuse: bool = False,
    workers: int = 1,
    config: DemConfig | None = None,
    run_id: str | None = None,
    resume: bool = False,
    overwrite: bool = False,
) -> Path:
    """Produceer het Alkmaar-proefgebied; bereid ontbrekende gebouw-ID's expliciet voor."""
    store = data_store or DataStore()
    config = config or DemConfig()
    tiles_path = landuse_run / "tiles.gpkg"
    selected = select_alkmaar_tiles(read_tiles(tiles_path))
    metadata = json.loads((landuse_run / "run.json").read_text(encoding="utf-8"))
    resolution = metadata["parameters"]["resolution_m"]
    mapping = landuse_run / "landgebruik_met_code.csv"
    source_paths = {
        name: Path(value["path"]) if value else None
        for name, value in metadata["inputs"].items()
    }
    sources = FunctioneelLandgebruikSources(
        **{
            name: source_paths[name]
            for name in FunctioneelLandgebruikSources.__dataclass_fields__
            if name in source_paths
        }
    )
    with production_run(
        output_root or store.processed_data_dir,
        "dem",
        "alkmaar",
        run_id=run_id,
        resume=resume,
        overwrite=overwrite,
        parameters={
            "config": json.loads(json.dumps(asdict(config))),
            "landuse_run": str(landuse_run.resolve()),
            "prepare_landuse": prepare_landuse,
            "tile_ids": selected.tile_id.tolist(),
            "resolution_m": resolution,
        },
    ) as run:
        configure_logging(log_file=run.path / "productie.log", stdout=True)
        logger = get_logger(__name__)
        logger.info("Alkmaar-proef: vier tegels, %s m resolutie", resolution)
        write_geopackage_layer_atomically(
            selected, run.path / "tiles.gpkg", layer_name="tiles"
        )
        if prepare_landuse:
            run.record_inputs(
                {
                    "landuse_metadata": landuse_run / "run.json",
                    "tile_index": tiles_path,
                    "mapping": mapping,
                    **vars(sources),
                }
            )
            paths = bouw_functioneel_landgebruik_tiles(
                run.path / "landgebruik" / "tiles",
                tiles_path=tiles_path,
                tile_ids=selected.tile_id.tolist(),
                workers=workers,
                resolution_m=resolution,
                sources=sources,
                mapping_csv=mapping,
                gap_fill_distance_m=metadata["parameters"].get(
                    "gap_fill_distance_m", 1.0
                ),
                write_building_ids=True,
                building_context_m=config.building_max_search_distance_m,
                overwrite=overwrite,
                download_missing_sources=True,
            )
        else:
            paths = [
                landuse_run
                / "tiles"
                / tile_filename("functioneel_landgebruik", tile_from_row(row))
                for _, row in selected.iterrows()
            ]
            inputs = {"tile_index": tiles_path}
            for number, path in enumerate(paths):
                inputs[f"landuse_{number}"] = path
                inputs[f"sources_{number}"] = path.parent / "bronnen" / path.name
                inputs[f"ids_{number}"], inputs[f"buildings_{number}"] = building_paths(
                    path
                )
            run.record_inputs(inputs)
        for name, files in (
            ("functioneel_landgebruik", paths),
            (
                "functioneel_landgebruik_bronnen",
                [path.parent / "bronnen" / path.name for path in paths],
            ),
            (
                "functioneel_landgebruik_gebouw_ids",
                [building_paths(path)[0] for path in paths],
            ),
        ):
            create_vrt_file(run.path / "landgebruik" / f"{name}.vrt", files=files)
        if ahn_vrt is None:
            area = box(*selected.total_bounds).buffer(
                config.interpolation_max_distance_m + resolution
            )
            for path in paths:
                buildings = wgpd.read_file(building_paths(path)[1], layer="gebouwen")
                if not buildings.empty:
                    area = area.union(
                        box(*buildings.total_bounds).buffer(
                            config.building_max_search_distance_m + resolution
                        )
                    )
            indices = get_tiles_features(
                ahn_service=AHNService(service="ahn_pdok"), poly_mask=box(*area.bounds)
            ).index.tolist()
            ahn_dir = download_ahn(
                ahn_dir=store.ahn_dir,
                select_indices=indices,
                model="dtm",
                cell_size="05",
                missing_only=True,
                create_vrt=False,
            )
            ahn_vrt = create_vrt_file(
                run.path / "input" / "ahn.vrt",
                files=[ahn_dir / f"{index}.tif" for index in indices],
            )
        result = bouw_dem_tiles(
            run.path,
            ahn_vrt_path=ahn_vrt,
            landuse_tiles=paths,
            config=config,
            overwrite=overwrite,
            workers=1,  # Preserve the legacy workflow's sequential DEM stage.
        )
        for name in ("dem", "dem_bron"):
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
                for _, window in cog.block_windows(1):
                    if not np.array_equal(
                        vrt.read(1, window=window),
                        cog.read(1, window=window),
                        equal_nan=True,
                    ):
                        raise ValueError(f"VRT/COG pixels wijken af: {name}")
        logger.info(
            "Alkmaar-validatie geslaagd: vier tegelkernen en identieke VRT/COG-pixels"
        )
        return result


def main(
    *,
    area: Area = Area.nederland,
    landuse_run: Path | None = None,
    data_store: DataStore | None = None,
    output_root: Path | None = None,
    ahn_vrt: Path | None = None,
    prepare_landuse: bool = False,
    workers: int | None = None,
    config: DemConfig | None = None,
    run_id: str | None = None,
    resume: bool = False,
    overwrite: bool = False,
) -> Path:
    """Resolve area-specific land use, then produce or resume the DEM."""
    area = Area(area)
    store = data_store or DataStore()
    config = config or DemConfig()
    legacy_metadata = None
    if (resume or overwrite) and run_id and area == Area.alkmaar:
        metadata_path = (
            (output_root or store.processed_data_dir)
            / "dem"
            / "alkmaar"
            / run_id
            / "run.json"
        )
        if metadata_path.exists():
            previous = json.loads(metadata_path.read_text(encoding="utf-8"))
            if "workflow_version" not in previous.get("parameters", {}):
                legacy_metadata = previous["parameters"]
                if landuse_run is None:
                    landuse_run = Path(legacy_metadata["landuse_run"])
    if prepare_landuse or legacy_metadata is not None:
        # Preserve explicitly invoked old Alkmaar runs and their manifest schema.
        if landuse_run is None:
            raise ValueError("Legacy --prepare-landuse requires --landuse-run")
        get_logger(__name__).warning(
            "--prepare-landuse is deprecated; using the legacy Alkmaar workflow"
        )
        return _legacy_main(
            landuse_run=landuse_run,
            data_store=store,
            output_root=output_root,
            ahn_vrt=ahn_vrt,
            prepare_landuse=legacy_metadata["prepare_landuse"]
            if legacy_metadata is not None
            else True,
            workers=resolve_workers(workers, settings.functioneel_landgebruik_workers),
            config=config,
            run_id=run_id,
            resume=resume,
            overwrite=overwrite,
        )
    workers = resolve_workers(workers, settings.dem_workers)
    with production_run(
        output_root or store.processed_data_dir,
        "dem",
        area.value,
        run_id=run_id,
        resume=resume,
        overwrite=overwrite,
        parameters={
            "workflow_version": 2,
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
            inputs[f"sources_{number}"] = path.parent / "bronnen" / path.name
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
        )
        for name in ("dem", "dem_bron"):
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
                for _, window in cog.block_windows(1):
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
    parser.add_argument("--prepare-landuse", action="store_true")
    parser.add_argument("--workers", type=int)
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
