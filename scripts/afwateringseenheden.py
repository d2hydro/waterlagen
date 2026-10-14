"""Produceer afwateringseenheden voor een gedeeld invoergebied."""

from pathlib import Path

from waterlagen._cli import production_parser, run_cli
from waterlagen.afwateringseenheden import read_brandlagen_config
from waterlagen.afwateringseenheden.productie import main


def _config(arguments: dict) -> dict:
    path = arguments.pop("brandlagen_config")
    if path is not None:
        try:
            arguments["brandlagen"] = read_brandlagen_config(path)
        except (OSError, TypeError) as error:
            raise ValueError(
                f"Kan brandlagen-configuratie {path} niet lezen: {error}"
            ) from error
    return arguments


def cli() -> None:
    """Run the area production with the shared CLI contract."""
    parser = production_parser(__doc__, workers=True)
    parser.add_argument(
        "--brandlagen-config",
        type=Path,
        help="TOML met optionele brandlagen, laagdefaults en globale defaults",
    )
    run_cli(parser, main, transform=_config)


if __name__ == "__main__":
    cli()
