"""Bestuurlijke gebieden downloaden. Landelijke bron; de gebiedsselectie volgt bij het verwerken."""

from pathlib import Path

from waterlagen.administratieve_gebieden import download_bestuurlijke_gebieden
from waterlagen.administratieve_gebieden import DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR
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
        result = download_bestuurlijke_gebieden(
            year=DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
            download_dir=store.administratieve_gebieden_dir,
            overwrite=OVERWRITE,
        )
    print(result.target_path)
