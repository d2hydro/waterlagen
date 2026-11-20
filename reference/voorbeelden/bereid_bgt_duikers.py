"""Selecteer BGT-duikers voor Aa en Maas inclusief rekentegels en buffers."""

from pathlib import Path

from shapely.ops import unary_union

from waterlagen._sources import SourcePreparation
from waterlagen.afwateringseenheden.tiles import (
    _calculation_geometry,
    _tiles_for_gebied,
)
from waterlagen.areas import resolve_area
from waterlagen.bgt.duikers import prepare_bgt_culverts
from waterlagen.datastore import DataStore
from waterlagen.logger import production_logging

DATA_DIR = Path("data")
AREA = "38"  # Waterschap Aa en Maas.
OUTPUT_SUBDIR = Path("brandlagen/aa_en_maas")  # Onder processed_data.
OVERWRITE = False  # True vervangt een eerdere selectie.

if __name__ == "__main__":
    store = DataStore(
        data_dir=DATA_DIR,
        source_data_dir=DATA_DIR / "source_data",
        processed_data_dir=DATA_DIR / "processed_data",
    )
    source = store.bgt_dir / "bgt.gpkg"
    output = store.processed_data_dir / OUTPUT_SUBDIR / "bgt_duikers.gpkg"
    with production_logging():
        if output.exists() and not OVERWRITE:
            raise FileExistsError(
                f"{output} bestaat al. Kies een andere OUTPUT_SUBDIR of zet OVERWRITE = True."
            )
        if not source.is_file():
            raise FileNotFoundError(f"Bereid eerst de BGT-vlakken voor: {source}")
        # Alleen een ontbrekende waterschapsgrens wordt automatisch opgehaald.
        area = resolve_area(AREA, store, SourcePreparation())
        tiles = _tiles_for_gebied(
            area.geometry, tile_size_m=10000, origin_x=0, origin_y=0
        )
        selection = unary_union(
            [_calculation_geometry(tile, tile_buffer_m=2000) for tile in tiles]
        )
        prepare_bgt_culverts(source, output, selection)
    print(output)
