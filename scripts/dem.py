"""Produceer eerst vier aangrenzende DEM-tegels rond Alkmaar."""

import argparse
import json
from dataclasses import asdict
from multiprocessing import freeze_support
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import box

from waterlagen import _geopandas as wgpd
from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._production import add_run_arguments, production_run
from waterlagen.ahn import AHNService, download_ahn, get_tiles_features
from waterlagen.datastore import DataStore
from waterlagen.dem import DemConfig, bouw_dem_tiles
from waterlagen.functioneel_landgebruik import (
    FunctioneelLandgebruikSources,
    bouw_functioneel_landgebruik_tiles,
)
from waterlagen.functioneel_landgebruik.gebouwen import building_paths
from waterlagen.logger import configure_logging, get_logger
from waterlagen.raster.tiles import read_tiles, tile_filename, tile_from_row
from waterlagen.raster.vrt import create_vrt_file


def select_alkmaar_tiles(tiles: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Selecteer een 2x2-blok uit het bestaande rooster, rond RD (111000, 516000)."""
    sizes = (tiles.xmax - tiles.xmin).unique()
    if len(sizes) != 1 or not (tiles.ymax - tiles.ymin).eq(sizes[0]).all():
        raise ValueError("Landgebruik vereist een regelmatig vierkant tegelrooster")
    size = int(sizes[0])
    origin_x, origin_y = int(tiles.xmin.min()), int(tiles.ymin.min())
    corner_x = origin_x + round((111000 - origin_x) / size) * size
    corner_y = origin_y + round((516000 - origin_y) / size) * size
    selected = tiles[
        tiles.xmin.isin([corner_x - size, corner_x])
        & tiles.ymin.isin([corner_y - size, corner_y])
    ]
    if len(selected) != 4:
        raise ValueError("Rooster bevat geen volledig 2x2-blok rond Alkmaar")
    return selected.sort_values(["ymin", "xmin"]).reset_index(drop=True)


def main(
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


if __name__ == "__main__":
    freeze_support()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--landuse-run", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--ahn-vrt", type=Path)
    parser.add_argument("--prepare-landuse", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
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
