"""Download de handmatig gepubliceerde landelijke Rijkswaterenbron."""

from pathlib import Path

from waterlagen.datastore import DataStore
from waterlagen.logger import production_logging
from waterlagen.rijkswateren import download_rijkswateren

DATA_DIR = Path("data")
OVERWRITE = False

if __name__ == "__main__":
    store = DataStore(
        data_dir=DATA_DIR,
        source_data_dir=DATA_DIR / "source_data",
        processed_data_dir=DATA_DIR / "processed_data",
    )
    with production_logging():
        path = download_rijkswateren(store.hydamo_dir, overwrite=OVERWRITE)
        print(path)
