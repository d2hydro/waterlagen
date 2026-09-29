"""Maak OSM-drinkwatervlakken voor de BAG-koppeling in functioneel landgebruik."""

import argparse
from pathlib import Path

from waterlagen.functioneel_landgebruik.osm_drinkwater import (
    OVERPASS_ENDPOINT,
    download_osm_drinkwater,
)
from waterlagen.logger import configure_logging


def main() -> Path:
    """Read CLI options and store validated source polygons as a GeoPackage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Uitvoerpad; standaard source_data/osm/drinkwaterlocaties.gpkg.",
    )
    parser.add_argument("--endpoint", default=OVERPASS_ENDPOINT)
    parser.add_argument("--timeout", type=float, default=150)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--include-building-contours",
        action="store_true",
        help="Neem losse gebouwcontouren ook mee in de BAG-koppellaag.",
    )
    arguments = parser.parse_args()
    if arguments.offline and arguments.cache_dir is None:
        parser.error("--offline vereist --cache-dir")
    configure_logging()
    return download_osm_drinkwater(
        target_path=arguments.output,
        endpoint=arguments.endpoint,
        cache_dir=arguments.cache_dir,
        offline=arguments.offline,
        overwrite=arguments.overwrite,
        include_buildings=arguments.include_building_contours,
        timeout=arguments.timeout,
    )


if __name__ == "__main__":
    main()
