"""Produceer DEM voor een gedeeld invoergebied."""

from pathlib import Path

if __name__ == "__main__":
    from _datastore_select import select_datastore

    select_datastore()

from waterlagen._cli import positive_int, production_parser, run_cli
from waterlagen.dem import DemConfig
from waterlagen.dem.workflow import main


def _config(arguments: dict) -> dict:
    version = arguments.get("ahn_version")
    arguments["ahn_version"] = None if version in (None, "latest") else int(version)
    values = {
        name: arguments.pop(name)
        for name in DemConfig.__dataclass_fields__
        if name != "output"
    }
    arguments["config"] = DemConfig(**values)
    return arguments


def cli() -> None:
    """Run DEM production with the common CLI contract."""
    parser = production_parser(__doc__, workers=True)
    parser.add_argument(
        "--landuse-run", type=Path, help="Expliciete bestaande landgebruikrun"
    )
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument(
        "--ahn-vrt", type=Path, help="Eigen maaiveldmodel (.vrt), standaard AHN"
    )
    sources.add_argument(
        "--ahn-version",
        choices=("latest", "4", "5", "6"),
        help="Nieuwste per cel of vaste AHN-versie",
    )
    parser.add_argument(
        "--building-workers", type=positive_int, help="Werkprocessen voor gebouwhoogten"
    )
    defaults = DemConfig()
    help_text = {
        "building_initial_buffer_m": "Eerste zoekafstand rond gebouwen in meters",
        "building_buffer_step_m": "Toename van de gebouwzoekafstand in meters",
        "building_percentile": "Hoogtepercentiel bij de eerste geslaagde zoekactie (0-100)",
        "building_offset_m": "Toeslag op de geschatte gebouwhoogte in meters (standaard 0.05; 0 schakelt de toeslag uit)",
        "building_max_search_distance_m": "Maximale zoekafstand rond gebouwen in meters",
        "interpolation_max_distance_m": "Maximale AHN-interpolatieafstand in meters; 0 schakelt vullen uit",
    }
    for name, description in help_text.items():
        parser.add_argument(
            "--" + name.replace("_", "-"),
            type=float,
            default=getattr(defaults, name),
            help=description,
        )
    run_cli(parser, main, transform=_config)


if __name__ == "__main__":
    cli()
