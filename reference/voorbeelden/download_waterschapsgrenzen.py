"""Waterschapsgrenzen downloaden. Alle waterschapsgrenzen in één GeoPackage."""

from pathlib import Path

from waterlagen.administratieve_gebieden import download_waterschapsgrenzen
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
        result = download_waterschapsgrenzen(
            download_dir=store.administratieve_gebieden_dir, overwrite=OVERWRITE
        )
    print(result.target_path)
