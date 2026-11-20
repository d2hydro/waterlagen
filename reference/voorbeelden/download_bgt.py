"""BGT downloaden. Kleine BGT-aanvraag; houd deze apart van de landelijke productiebron."""

from pathlib import Path

from waterlagen.bgt import bgt_custom_download
from waterlagen.areas import NAMED_AREAS
from waterlagen.datastore import DataStore
from waterlagen.logger import production_logging

DATA_DIR = Path("data")  # Pas aan naar een map met voldoende vrije ruimte.
OVERWRITE = False  # True vervangt bestaande bronbestanden.
AREA = "alkmaar_centrum"
FEATURETYPES = ("waterdeel", "pand")

if __name__ == "__main__":
    store = DataStore(
        data_dir=DATA_DIR,
        source_data_dir=DATA_DIR / "source_data",
        processed_data_dir=DATA_DIR / "processed_data",
    )
    with production_logging():
        result = bgt_custom_download(
            download_dir=store.bgt_dir / AREA,
            featuretypes=FEATURETYPES,
            poly_mask=NAMED_AREAS[AREA],
            overwrite=OVERWRITE,
        )
    print(result.download_dir)
