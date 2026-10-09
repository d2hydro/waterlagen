"""Common command-line contract for the five production entry points."""

import argparse
from collections.abc import Callable, Sequence
from multiprocessing import freeze_support
from pathlib import Path

from waterlagen._production import add_run_arguments, validate_run_options
from waterlagen._run_logging import production_logging
from waterlagen.areas import area_name
from waterlagen.datastore import DataStore
from waterlagen.logger import get_logger


def positive_int(value: str) -> int:
    """Parse a strictly positive command-line integer."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Moet minstens 1 zijn")
    return number


def production_parser(
    description: str, *, workers: bool = False
) -> argparse.ArgumentParser:
    """Build shared help, area, storage, source and run options."""
    parser = argparse.ArgumentParser(
        description=description,
        allow_abbrev=False,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--area",
        default="nederland",
        help="Invoergebied: nederland, alkmaar of waterschap_CODE; uitvoer wordt niet afgeknipt",
    )
    selection.add_argument(
        "--waterbeheercode",
        help="Waterschapscode als gebiedsselectie, zonder beheerderfilter op objecten",
    )
    parser.add_argument(
        "--data-dir", type=Path, help="Gegevensmap; standaard uit DataStore/.datastore"
    )
    parser.add_argument(
        "--output-root", type=Path, help="Productiemap; standaard processed_data_dir"
    )
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument(
        "--refresh-sources",
        action="store_true",
        help="Bronnen vernieuwen; vereist een nieuwe run",
    )
    sources.add_argument(
        "--offline",
        action="store_true",
        help="Alleen lokale bronnen gebruiken; ontbrekende bronnen geven een fout",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Diagnostische details in het productielog opnemen",
    )
    if workers:
        parser.add_argument(
            "--workers",
            type=positive_int,
            help="Aantal werkprocessen; standaard de productinstelling",
        )
    add_run_arguments(parser)
    return parser


def run_cli(
    parser: argparse.ArgumentParser,
    workflow: Callable[..., Path],
    argv: Sequence[str] | None = None,
    *,
    transform: Callable[[dict], dict] | None = None,
) -> None:
    """Validate before I/O, configure logging explicitly, then invoke the Python API."""
    freeze_support()
    arguments = vars(parser.parse_args(argv))
    debug = arguments.pop("debug")
    data_dir = arguments.pop("data_dir")
    output_root = arguments.pop("output_root")
    try:
        arguments["area"] = area_name(
            arguments.pop("waterbeheercode") or arguments["area"]
        )
        validate_run_options(
            arguments["run_id"],
            resume=arguments["resume"],
            overwrite=arguments["overwrite"],
        )
        if arguments["refresh_sources"] and (
            arguments["resume"] or arguments["overwrite"]
        ):
            raise ValueError("--refresh-sources vereist een nieuwe run")
        if transform is not None:
            arguments = transform(arguments)
    except ValueError as error:
        parser.error(str(error))
    options = {}
    if data_dir is not None:
        options.update(
            data_dir=data_dir,
            source_data_dir=data_dir / "source_data",
            processed_data_dir=data_dir / "processed_data",
        )
    if output_root is not None:
        options["processed_data_dir"] = output_root
    with production_logging(debug=debug):
        try:
            result = workflow(data_store=DataStore(**options), **arguments)
        except Exception:  # noqa: BLE001 - application boundary reports errors with a nonzero exit
            get_logger(__name__).exception("Productie mislukt")
            raise SystemExit(1) from None
        get_logger(__name__).info("Productie voltooid: %s", result)
