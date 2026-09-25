# %%
"""Maak een testuitsnede van drie gemaalobjecten in hetzelfde pomphuis."""

from dataclasses import replace
from pathlib import Path

from controle_bag_landgebruik import main as controle_bag

from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik import (
    FunctioneelLandgebruikSources,
    bouw_functioneel_landgebruik,
)
from waterlagen.functioneel_landgebruik.landgebruikstabel import DEFAULT_MAPPING_CSV
from waterlagen.logger import configure_logging

# Gemaal Lely: drie afzonderlijke bronobjecten (afdelingen 2, 3 en 4).
# BAG-pand 0463100000001005 heeft overige gebruiksfunctie.
# Huidige bron: 3 x 450 = 1350 m³/min, dus klasse >1000 (43/171).
BOUNDS = (135600.0, 531900.0, 136100.0, 532400.0)  # RD, 500 x 500 meter
LANDGEBRUIK_CSV = DEFAULT_MAPPING_CSV
BGT_FILENAME = "bgt.gpkg"


def main() -> Path:
    """Write the control layers and raster for Lely, replacing this example only."""
    store = DataStore()
    output = (
        store.processed_data_dir / "functioneel_landgebruik" / "controle_gemalen_lely"
    )
    sources = replace(
        FunctioneelLandgebruikSources.from_datastore(store),
        bgt_gpkg=store.bgt_dir / BGT_FILENAME,
    )
    if not sources.bgt_gpkg.is_file():
        raise FileNotFoundError(f"BGT-bestand ontbreekt: {sources.bgt_gpkg}")
    if sources.gemalen_gpkg is None:
        raise FileNotFoundError("HyDAMO-bron ontbreekt: source_data/hydamo/hydamo.gpkg")
    output.mkdir(parents=True, exist_ok=True)
    configure_logging(log_file=output / "berekening.log")
    control = controle_bag(
        store,
        bounds=BOUNDS,
        overwrite=True,
        stap=6,
        mapping_csv=LANDGEBRUIK_CSV,
        gemalen_gpkg=sources.gemalen_gpkg,
        target_path=output / "controle.gpkg",
    )
    raster = bouw_functioneel_landgebruik(
        output / "landgebruik.tif",
        bounds=BOUNDS,
        resolution_m=0.5,
        sources=sources,
        mapping_csv=LANDGEBRUIK_CSV,
        download_missing_sources=False,
        overwrite=True,
    )
    print(f"Panden en gemaalpunten: {control}")
    print(f"Landgebruiksraster en QML-legenda: {raster}")
    return output


if __name__ == "__main__":
    main()
