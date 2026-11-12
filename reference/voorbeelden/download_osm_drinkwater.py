"""OSM-drinkwaterlocaties downloaden. Landelijke selectie van beoordeelde locaties, geen volledige OSM-download."""

from pathlib import Path

from waterlagen.functioneel_landgebruik.osm_drinkwater import download_osm_drinkwater
from waterlagen.datastore import DataStore
from waterlagen.logger import production_logging

DATA_DIR = Path("data")  # Pas aan naar een map met voldoende vrije ruimte.
OVERWRITE = False  # True vervangt bestaande bronbestanden.

if __name__ == "__main__":
    store = DataStore(
        data_dir=DATA_DIR,
        source_data_dir=DATA_DIR / "source_data",
        processed_data_dir=DATA_DIR / "processed_data",
    )
    with production_logging():
        result = download_osm_drinkwater(data_store=store, overwrite=OVERWRITE)
    print(result)
