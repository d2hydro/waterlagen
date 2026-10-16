"""Produceer afwateringseenheden voor een gedeeld invoergebied."""

from pathlib import Path

from waterlagen._cli import production_parser, run_cli
from waterlagen.afwateringseenheden import read_brandlagen_config
from waterlagen.afwateringseenheden.productie import main
from waterlagen.afwateringseenheden.sources import validate_authority_options
from waterlagen.rijkswateren.download import RIJKSWATEREN_URL


def _config(arguments: dict) -> dict:
    area = arguments["area"]
    code = None
    if isinstance(area, str) and area.startswith("waterschap_"):
        code = area.removeprefix("waterschap_")
    validate_authority_options(
        code, arguments["overige_waterschappen"], arguments["eigen_hydamo"]
    )
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
        "--overige-waterschappen",
        action="store_true",
        help="Ook overige waterschappen als doelen; vereist een waterschapscode",
    )
    parser.add_argument(
        "--eigen-hydamo",
        type=Path,
        help="GeoPackage ter vervanging van hydroobject, gemaal, stuw en duikersifonhevel van het gekozen waterschap",
    )
    parser.add_argument(
        "--rijkswateren-url",
        default=RIJKSWATEREN_URL,
        help="Openbare Rijkswateren-share of directe GeoPackage-URL",
    )
    parser.add_argument(
        "--brandlagen-config",
        type=Path,
        help="TOML met optionele brandlagen, laagdefaults en globale defaults",
    )
    parser.add_argument(
        "--duiker-tolerance",
        type=float,
        default=0.5,
        help="Maximale koppelafstand per duikeruiteinde in meters (0.5)",
    )
    parser.add_argument(
        "--max-aansluitlengte",
        type=float,
        default=None,
        help="Maximale lengte van directe aansluitstukken zonder afwateringsdoel",
    )
    run_cli(parser, main, transform=_config)


if __name__ == "__main__":
    cli()
