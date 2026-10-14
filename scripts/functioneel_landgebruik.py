"""Produceer functioneel landgebruik voor een gedeeld invoergebied."""

from pathlib import Path

from waterlagen._cli import production_parser, run_cli
from waterlagen.functioneel_landgebruik.productie import main


def cli() -> None:
    """Run the land-use production CLI."""
    parser = production_parser(__doc__, workers=True)
    parser.add_argument("--mapping-csv", type=Path, help="Eigen landgebruikscodetabel")
    parser.add_argument(
        "--bgt-path",
        type=Path,
        help="Expliciet voorbereid BGT-bestand; geen BGT-download",
    )
    parser.add_argument(
        "--building-context-m",
        type=float,
        default=5.0,
        help="Gebouwcontext voor DEM in meters",
    )
    run_cli(parser, main)


if __name__ == "__main__":
    cli()
