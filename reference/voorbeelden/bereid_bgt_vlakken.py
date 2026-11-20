"""Zet de eerder gedownloade landelijke BGT-ZIP om naar bgt.gpkg."""

from pathlib import Path

from waterlagen.bgt.productie import main
from waterlagen.datastore import DataStore
from waterlagen.logger import production_logging

DATA_DIR = Path("data")
WORKERS = 8
OVERWRITE = False  # True bouwt opnieuw op, bijvoorbeeld na een nieuwe ZIP.

if __name__ == "__main__":
    store = DataStore(
        data_dir=DATA_DIR,
        source_data_dir=DATA_DIR / "source_data",
        processed_data_dir=DATA_DIR / "processed_data",
    )
    # Invoer: store.bgt_dir / "bgt-gmllight-nl-nopbp.zip".
    # Uitvoer: store.bgt_dir / "bgt.gpkg".
    with production_logging():
        result = main(data_store=store, overwrite=OVERWRITE, workers=WORKERS)
    print(result)
