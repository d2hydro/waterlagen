"""TOP10NL downloaden. Grote landelijke download; Alkmaar-centrum beperkt dit bestand niet."""

from pathlib import Path

from waterlagen.top10nl import download_top10nl
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
        result = download_top10nl(download_dir=store.top10nl_dir, overwrite=OVERWRITE)
    print(result)
