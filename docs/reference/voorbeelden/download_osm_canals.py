"""Open OSM-kanalen downloaden voor Aa en Maas inclusief tegelbuffers."""

from pathlib import Path

from waterlagen.datastore import DataStore
from waterlagen.logger import production_logging
from waterlagen.osm_waterlopen import download_osm_canals

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
