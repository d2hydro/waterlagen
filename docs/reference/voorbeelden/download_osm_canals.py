"""OSM-waterlopen en duikers downloaden voor Aa en Maas inclusief tegelbuffers."""

from pathlib import Path

from waterlagen.datastore import DataStore
from waterlagen.logger import production_logging
from waterlagen.osm_waterlopen import (
    download_osm_canals,
    download_osm_culverts,
    download_osm_waterlopen,
)

DATA_DIR = Path("data")  # Pas aan naar de gebruikte datastore.
BOUNDS = (128000, 368000, 212000, 432000)  # EPSG:28992; Aa en Maas met tegelbuffers.
OVERWRITE = False

if __name__ == "__main__":
    store = DataStore(
        data_dir=DATA_DIR,
        source_data_dir=DATA_DIR / "source_data",
        processed_data_dir=DATA_DIR / "processed_data",
    )
    with production_logging():
        result = download_osm_canals(BOUNDS, data_store=store, overwrite=OVERWRITE)
        print(result)
        for waterway in ("ditch", "drain", "stream"):
            result = download_osm_waterlopen(
                BOUNDS, waterway=waterway, data_store=store, overwrite=OVERWRITE
            )
            print(result)
        result = download_osm_culverts(BOUNDS, data_store=store, overwrite=OVERWRITE)
        print(result)
