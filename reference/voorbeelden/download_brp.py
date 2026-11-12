"""BRP downloaden. Landelijke download; een bestaand brp.gpkg wordt hergebruikt."""

from pathlib import Path

from waterlagen.brp import download_brp
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
        result = download_brp(
            download_dir=store.brp_dir, filename="brp.gpkg", overwrite=OVERWRITE
        )
    print(result.path)
