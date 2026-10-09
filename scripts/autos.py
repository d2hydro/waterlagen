"""Produceer autos met volledige CBS-buurtcontext."""

from waterlagen._cli import production_parser, run_cli
from waterlagen.autos.productie import main


def cli() -> None:
    """Start production with the shared command-line contract."""
    parser = production_parser(__doc__)
    parser.add_argument(
        "--no-geoparquet",
        dest="write_geoparquet",
        action="store_false",
        help="Alleen GeoPackage schrijven",
    )
    run_cli(parser, main)


if __name__ == "__main__":
    cli()
