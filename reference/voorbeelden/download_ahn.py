"""AHN downloaden. Hele AHN-tegels rond Alkmaar-centrum; dit is geen uitsnede van 1 km²."""

from pathlib import Path

from waterlagen.ahn import download_ahn
from waterlagen.areas import NAMED_AREAS
from waterlagen.datastore import DataStore
from waterlagen.logger import production_logging

DATA_DIR = Path("data")  # Pas aan naar een map met voldoende vrije ruimte.
OVERWRITE = False  # True vervangt bestaande bronbestanden.
AREA = "alkmaar_centrum"
AHN_VERSION = 4
MODEL = "dtm"

if __name__ == "__main__":
    store = DataStore(
        data_dir=DATA_DIR,
        source_data_dir=DATA_DIR / "source_data",
        processed_data_dir=DATA_DIR / "processed_data",
    )
    with production_logging():
        result = download_ahn(
            ahn_dir=store.ahn_dir,
            poly_mask=NAMED_AREAS[AREA],
            model=MODEL,
            ahn_version=AHN_VERSION,
            service="ahn_pdok",
            cell_size="05",
            missing_only=not OVERWRITE,
            create_vrt=True,
        )
    print(result)
