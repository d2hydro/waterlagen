"""Dijkringen downloaden. Landelijke historische dijkringen, geen actuele gebiedsindeling."""

from pathlib import Path

from waterlagen.dijkringen import download_dijkringen
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
        result = download_dijkringen(
            download_dir=store.dijkringen_dir, overwrite=OVERWRITE
        )
    print(result.target_path)
