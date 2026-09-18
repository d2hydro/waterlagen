"""Command-line entry points for installed Waterlagen workflows."""

import argparse
import math
import multiprocessing
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from waterlagen import __version__, datastore
from waterlagen.datastore import DataStore
from waterlagen.logger import get_logger, init_logger

logger = get_logger(__name__)


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("gebruik een geheel getal van minimaal 1")
    return number


def _nonnegative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("gebruik een eindig getal van minimaal 0")
    return number


def _positive_float(value: str) -> float:
    number = _nonnegative_float(value)
    if number == 0:
        raise argparse.ArgumentTypeError("gebruik een getal groter dan 0")
    return number


def _authority_code(value: str) -> str:
    if re.fullmatch(r"[0-9]{1,4}", value) is None:
        raise argparse.ArgumentTypeError("gebruik een waterbeheercode, bijvoorbeeld 38")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="waterlagen", description="GIS-basislagen produceren voor waterbeheer."
    )
    parser.add_argument(
        "--version", action="version", version=f"Waterlagen {__version__}"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "controleer", help="Controleer installatie en opslag zonder downloads."
    )
    production = commands.add_parser(
        "afwateringseenheden", help="Bereken afwateringseenheden voor een waterschap."
    )
    for command in (check, production):
        command.add_argument(
            "--data-dir",
            type=Path,
            metavar="MAP",
            help="Hoofdmap voor alle downloads en resultaten; overschrijft de opslagconfiguratie.",
        )
    production.add_argument(
        "--waterschap",
        type=_authority_code,
        default="38",
        help="Waterbeheercode (standaard: 38, Aa en Maas).",
    )
    production.add_argument(
        "--workers",
        type=_positive_int,
        help="Aantal processen; standaard uit .env, anders 4.",
    )
    production.add_argument(
        "--buffer-m",
        type=_nonnegative_float,
        default=2000,
        help="Gebiedsbuffer in meters (standaard: 2000).",
    )
    production.add_argument(
        "--tile-size-m",
        type=_positive_float,
        default=10000,
        help="Zijde van de rekentegel in meters (standaard: 10000).",
    )
    production.add_argument(
        "--tile-buffer-m",
        type=_nonnegative_float,
        default=2000,
        help="Tegelbuffer in meters (standaard: 2000).",
    )
    production.add_argument(
        "--burn-depth-m",
        type=_nonnegative_float,
        default=100,
        help="Branddiepte voor secundaire waterlopen in meters (standaard: 100).",
    )
    production.add_argument(
        "--max-fill-depth-m",
        type=_nonnegative_float,
        default=50,
        help="Maximale vuldiepte in meters (standaard: 50).",
    )
    production.add_argument(
        "--seed",
        type=_positive_int,
        default=12345,
        help="Vaste PCRaster-seed per tegel (standaard: 12345).",
    )
    return parser


def _configure_storage(data_dir: Path | None) -> DataStore:
    """Set storage before importing downloaders and propagate it to workers."""
    if data_dir is None:
        selected = DataStore()
    else:
        root = data_dir.expanduser().resolve()
        selected = DataStore(
            data_dir=root,
            source_data_dir=root / "source_data",
            processed_data_dir=root / "processed_data",
            _env_file=None,
        )
    selected.data_dir = selected.data_dir.expanduser().resolve()
    selected.source_data_dir = selected.source_data_dir.expanduser().resolve()
    selected.processed_data_dir = selected.processed_data_dir.expanduser().resolve()
    selected.data_dir.mkdir(parents=True, exist_ok=True)
    # Keep the exported instance: imported modules may hold a reference to it.
    for name in ("data_dir", "source_data_dir", "processed_data_dir"):
        value = getattr(selected, name)
        setattr(datastore, name, value)
        os.environ[name.upper()] = str(value)
    logger.info("Brongegevens: %s", selected.source_data_dir)
    logger.info("Resultaten: %s", selected.processed_data_dir)
    return selected


def _check_installation(data_store: DataStore) -> None:
    """Check native raster operations and writable storage without downloads."""
    import geopandas
    import numpy as np
    import rasterio
    from osgeo import gdal, gdal_array

    from waterlagen.afwateringseenheden.pcraster import require_pcraster

    pcraster = require_pcraster()
    pcraster.setclone(3, 3, 1.0, 0.0, 3.0)
    heights = np.arange(9, dtype=np.float32).reshape(3, 3)
    dem = pcraster.numpy2pcr(pcraster.Scalar, heights, -9999)
    ldd = pcraster.lddcreate(dem, 50, 1e31, 1e31, 1e31)
    directions = pcraster.pcr2numpy(ldd, 255)
    with TemporaryDirectory(
        prefix="installatiecontrole-", dir=data_store.data_dir
    ) as directory:
        path = Path(directory) / "controle.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=3,
            height=3,
            count=1,
            dtype="uint8",
            crs="EPSG:28992",
            transform=rasterio.transform.from_origin(0, 3, 1, 1),
        ) as raster:
            raster.write(directions.astype("uint8"), 1)
        with rasterio.open(path) as raster:
            if not np.array_equal(raster.read(1), directions):
                raise RuntimeError("Rastercontrole gaf een onverwacht resultaat.")
    logger.info(
        "Installatie OK: Waterlagen %s; GDAL %s; GeoPandas %s; Rasterio %s; PCRaster beschikbaar.",
        __version__,
        gdal.VersionInfo(),
        geopandas.__version__,
        rasterio.__version__,
    )
    logger.debug("GDAL NumPy-extensie: %s", gdal_array.__file__)


def main(argv: list[str] | None = None) -> int:
    """Run the Waterlagen command-line interface.

    Parameters
    ----------
    argv : list of str or None, optional
        Command arguments. None reads the process command line.

    Returns
    -------
    int
        Zero on success, one on execution failure, or 130 on interruption.
        Argument errors are reported by argparse with exit status two.
    """
    arguments = _parser().parse_args(argv)
    multiprocessing.freeze_support()
    init_logger(name="waterlagen")
    try:
        data_store = _configure_storage(arguments.data_dir)
        if arguments.command == "controleer":
            _check_installation(data_store)
        else:
            from waterlagen.afwateringseenheden.production import (
                ProductionConfig,
                produce_afwateringseenheden,
            )

            config = ProductionConfig(
                waterbeheercode=arguments.waterschap,
                workers=arguments.workers,
                buffer_m=arguments.buffer_m,
                tile_size_m=arguments.tile_size_m,
                tile_buffer_m=arguments.tile_buffer_m,
                burn_depth_m=arguments.burn_depth_m,
                max_fill_depth_m=arguments.max_fill_depth_m,
                random_seed=arguments.seed,
            )
            path = produce_afwateringseenheden(config, data_store=data_store)
            logger.info("Gereed. Open dit bestand in QGIS: %s", path)
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        logger.error("Uitvoering mislukt: %s", exc)
        return 1
    except KeyboardInterrupt:
        logger.error(
            "Uitvoering afgebroken. Een volgende start maakt een nieuwe uitvoermap."
        )
        return 130
    return 0
