# %%
import os
from multiprocessing import freeze_support
from pathlib import Path

from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik import bouw_functioneel_landgebruik_tiles
from waterlagen.logger import init_logger
from waterlagen.raster.inspect import inspect_raster
from waterlagen.raster.tiles import build_tiles
from waterlagen.raster.vrt import create_cog_file, create_vrt_file

REPO_ROOT = Path(__file__).resolve().parents[1]


def _safe_workers(max_workers: int = 3) -> int:
    return max(1, min(max_workers, os.cpu_count() or 1))


def main(data_store: DataStore | None = None) -> Path:
    data_store = data_store or DataStore(data_dir=REPO_ROOT / "data")
    init_logger(
        name="bouw landgebruik",
        debug=False,
        log_file=data_store.data_dir / "bouw_functioneel_landgebruik.log",
    )

    tiles_path = data_store.processed_data_dir / "tiles" / "tiles.gpkg"
    tiles_path = build_tiles(
        target_path=tiles_path,
        tile_size_m=5000,
        overwrite=False,
    )

    workers = _safe_workers()
    print(f"attempt to build with #workers: {workers}")

    data_dir = data_store.processed_data_dir / "functioneel_landgebruik"
    tiles_dir = data_dir / "tiles"
    tile_files = bouw_functioneel_landgebruik_tiles(
        target_dir=tiles_dir,
        tiles_path=tiles_path,
        workers=workers,
        data_store=data_store,
        overwrite=False,
    )

    print(f"Tiles built: {len(tile_files)}")

    print("Create VRT-file")
    vrt_file = create_vrt_file(
        vrt_file=data_dir / "functioneel_landgebruik.vrt", directory=tiles_dir
    )

    print(f"Create cog_file from vrt_file: {vrt_file}")
    cog_file = create_cog_file(
        vrt_file=vrt_file,
        cog_file=data_dir / "functioneel_landgebruik.tif",
        overwrite=False,
    )

    inspect_raster(cog_file)
    return cog_file


if __name__ == "__main__":
    freeze_support()
    main()
