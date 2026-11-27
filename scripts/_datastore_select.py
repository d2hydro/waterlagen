"""Selecteer het datastorebestand vóór het laden van productiemodules."""

import argparse
import os
from pathlib import Path


def select_datastore() -> None:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--datastore", type=Path)
    options, _ = parser.parse_known_args()
    if options.datastore is not None:
        if not options.datastore.is_file():
            parser.error(f"Datastorebestand ontbreekt: {options.datastore}")
        os.environ["WATERLAGEN_DATASTORE"] = str(options.datastore.resolve())
