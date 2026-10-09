"""Produceer functioneel landgebruik voor Nederland of Alkmaar."""

import argparse
from multiprocessing import freeze_support
from pathlib import Path

from waterlagen._production import add_run_arguments
from waterlagen.areas import Area
from waterlagen.functioneel_landgebruik.productie import main

if __name__ == "__main__":
    freeze_support()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", type=Area, choices=list(Area), default=Area.nederland)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--mapping-csv", type=Path)
    parser.add_argument("--building-context-m", type=float, default=5.0)
    add_run_arguments(parser)
    main(**vars(parser.parse_args()))
