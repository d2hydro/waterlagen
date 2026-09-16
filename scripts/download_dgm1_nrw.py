# %%
"""Download originele NRW DGM1-tegels via een gebied of lokale URL-lijst."""

import argparse
import sys
from pathlib import Path

from shapely.geometry.base import BaseGeometry

from waterlagen import _geopandas as wgpd
from waterlagen import settings
from waterlagen.dgm1 import download_dgm1 as _download_dgm1
from waterlagen.logger import configure_logging

URL_LIST: Path | None = None
MASK_PATH: Path | None = None
MASK_LAYER: str | None = None
WORKERS = 4
ATTEMPTS = 3
TIMEOUT_SECONDS = 60


def download_dgm1(
    url_list: Path | None = None,
    *,
    poly_mask: BaseGeometry | None = None,
) -> Path:
    """Download DGM1 vanuit het Interactive Window of de terminal.

    Parameters
    ----------
    url_list : pathlib.Path, optional
        Lokale downloadlijst. Standaard wordt URL_LIST uit het script gebruikt.
        Geef een lijst of poly_mask op, niet beide.
    poly_mask : shapely.geometry.base.BaseGeometry, optional
        Gebied in settings.crs. Selecteert tegels uit de actuele NRW-index.

    Returns
    -------
    pathlib.Path
        VRT van de geselecteerde originele tegels in UTM32/DHHN2016.
        Geldige bestaande tegels worden hergebruikt.
    """
    if url_list is not None and poly_mask is not None:
        raise ValueError("Geef een URL-lijst of poly_mask op, niet beide")
    if poly_mask is None and url_list is None:
        url_list = URL_LIST
    if poly_mask is None and url_list is None:
        raise ValueError("Geef een gebied op via MASK_PATH/poly_mask of een URL_LIST")
    configure_logging()
    return _download_dgm1(
        poly_mask=poly_mask,
        url_list=url_list,
        workers=WORKERS,
        retries=ATTEMPTS,
        timeout=TIMEOUT_SECONDS,
    )


def _read_mask(path: Path, layer: str | None) -> BaseGeometry:
    area = wgpd.read_file(path, layer=layer)
    if area.crs is None:
        raise ValueError(f"Gebied heeft geen CRS: {path}")
    return area.to_crs(settings.crs).geometry.make_valid().union_all()


def main() -> None:
    """Read terminal arguments and start the download."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url_list", nargs="?", type=Path, help="Tekstbestand met URL's")
    parser.add_argument(
        "--mask", type=Path, help="Vectorbestand met het downloadgebied"
    )
    parser.add_argument("--layer", help="Laag in het gebiedsbestand")
    args = parser.parse_args()
    if args.mask is not None and args.url_list is not None:
        parser.error("Gebruik een URL-lijst of --mask, niet beide")
    if args.url_list is not None:
        download_dgm1(args.url_list)
        return
    mask_path = args.mask if args.mask is not None else MASK_PATH
    mask_layer = args.layer if args.layer is not None else MASK_LAYER
    if mask_path is not None:
        download_dgm1(poly_mask=_read_mask(mask_path, mask_layer))
    else:
        if URL_LIST is None:
            parser.error("Geef --mask of een URL-lijst op")
        download_dgm1(URL_LIST)


if __name__ == "__main__":
    if "ipykernel" in sys.modules:
        if MASK_PATH is not None:
            download_dgm1(poly_mask=_read_mask(MASK_PATH, MASK_LAYER))
        else:
            download_dgm1(URL_LIST)
    else:
        main()
