"""LIWO downloaden. Volledig landelijk raster; geen gebiedsselectie bij de download."""

from pathlib import Path

from waterlagen.liwo import download_raster
from waterlagen.liwo import FILENAME
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
        result = download_raster(
            store.source_data_dir / "liwo" / FILENAME, overwrite=OVERWRITE
        )
    print(result)
