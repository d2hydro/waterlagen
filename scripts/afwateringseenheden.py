"""Produceer afwateringseenheden voor een gedeeld invoergebied."""

from waterlagen._cli import production_parser, run_cli
from waterlagen.afwateringseenheden.productie import main


def cli() -> None:
    """Run the area production with the shared CLI contract."""
    run_cli(production_parser(__doc__, workers=True), main)


if __name__ == "__main__":
    cli()
