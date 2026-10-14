"""Watersysteem voorbereiden en afwateringseenheden met eigen instellingen berekenen."""

from math import ceil, floor
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from waterlagen.administratieve_gebieden import (
    DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
    download_bestuurlijke_gebieden,
)
from waterlagen.afwateringseenheden import (
    calculate_afwateringseenheden_tiles,
    prepare_watersysteem,
    read_brandlagen,
    read_brandlagen_config,
    read_hydroobjecten,
    read_puntobjecten,
    write_watersysteem,
)
from waterlagen.ahn import download_ahn
from waterlagen.areas import NAMED_AREAS, NAMED_AREAS_CRS
from waterlagen.datastore import DataStore
from waterlagen.hydamo import download_hydamo
from waterlagen.logger import production_logging
from waterlagen.settings import settings

DATA_DIR = Path("data")
AREA = "alkmaar_centrum"
EXPERIMENT = "experiment_01"  # Nieuwe naam bij andere bronnen of rekeninstellingen.
TILE_SIZE_M = 1000  # Eén kerntegel voor dit vierkante voorbeeldgebied.
TILE_BUFFER_M = 2000
RESOLUTION_M = 2.0
TOLERANCE_M = 2.0
MAX_SEGMENT_LENGTH_M = 500.0
BURN_DEPTH_M = 100.0
MAX_FILL_DEPTH_M = 50.0
WORKERS = 1
BRANDLAGEN_CONFIG: Path | None = None  # Bijvoorbeeld Path("brandlagen.toml").

if __name__ == "__main__":
    store = DataStore(
        data_dir=DATA_DIR,
        source_data_dir=DATA_DIR / "source_data",
        processed_data_dir=DATA_DIR / "processed_data",
    )
    output_dir = (
        store.processed_data_dir
        / "voorbeelden"
        / AREA
        / EXPERIMENT
        / "afwateringseenheden"
    )
    gebied = (
        gpd.GeoSeries([NAMED_AREAS[AREA]], crs=NAMED_AREAS_CRS)
        .to_crs(settings.crs)
        .iloc[0]
    )
    # Voor dit voorbeeld ligt de tegel-oorsprong op de linkeronderhoek van het gebied.
    # Rond de dekking naar volledige tegels af voordat de buffer wordt toegevoegd.
    xmin, ymin, xmax, ymax = gebied.bounds
    origin_x, origin_y = floor(xmin), floor(ymin)
    tile_bounds = box(
        origin_x,
        origin_y,
        origin_x + ceil((xmax - origin_x) / TILE_SIZE_M) * TILE_SIZE_M,
        origin_y + ceil((ymax - origin_y) / TILE_SIZE_M) * TILE_SIZE_M,
    )
    context = tile_bounds.buffer(TILE_BUFFER_M).envelope

    with production_logging():
        # Optioneel: lees eigen QGIS-lagen; rastercelconflicten worden bij de
        # tegelvoorbereiding gecontroleerd op het daadwerkelijke rekenraster.
        brandlagen = None
        if BRANDLAGEN_CONFIG is not None:
            brandlagen = read_brandlagen_config(BRANDLAGEN_CONFIG)
            brandobjecten = read_brandlagen(brandlagen, spatial_selection=context)
            print("Optionele brandobjecten in het rekengebied:", len(brandobjecten))
        # 1. Bronnen ophalen. HYDAMO en de landsgrens zijn landelijke bestanden.
        hydamo = download_hydamo(download_dir=store.hydamo_dir, overwrite=False)
        landsgrens = download_bestuurlijke_gebieden(
            year=DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
            download_dir=store.administratieve_gebieden_dir,
            overwrite=False,
        )
        ahn = download_ahn(
            ahn_dir=store.ahn_dir,
            poly_mask=context,
            model="dtm",
            ahn_version=4,
            service="ahn_pdok",
            cell_size="05",
            missing_only=True,
            create_vrt=True,
        )

        # 2. Lees het watersysteem inclusief omgeving; pas de selectie hier aan.
        hydro = read_hydroobjecten(hydamo.target_path, spatial_selection=context)
        primair = hydro.loc[hydro.categorieoppwaterlichaam.eq("primair")].copy()
        secundair = hydro.loc[hydro.categorieoppwaterlichaam.eq("secundair")].copy()
        punten = read_puntobjecten(
            hydamo.target_path, layers=["gemaal", "stuw"], spatial_selection=context
        )
        netwerk = prepare_watersysteem(
            primair,
            punten,
            hydroobject_secundair=secundair,
            tolerance=TOLERANCE_M,
            max_length=MAX_SEGMENT_LENGTH_M,
        )
        watersysteem = write_watersysteem(
            hydroobject_primair=primair,
            hydroobject_secundair=secundair,
            watersysteem=netwerk,
            output_path=output_dir / "watersysteem.gpkg",
            secondary_connection_tolerance=TOLERANCE_M,
            overwrite=False,
        )

        # 3. Bereken de tegels en voeg ze samen. Pas parameters bovenaan aan.
        resultaat = calculate_afwateringseenheden_tiles(
            gebied,
            ahn_vrt_path=ahn,
            landsgrens_path=landsgrens.target_path,
            watersysteem_path=watersysteem,
            output_dir=output_dir / "tiles",
            merged_output_path=output_dir / "afwateringseenheden.gpkg",
            tile_size_m=TILE_SIZE_M,
            tile_buffer_m=TILE_BUFFER_M,
            origin_x=origin_x,
            origin_y=origin_y,
            resolution_m=RESOLUTION_M,
            burn_depth_m=BURN_DEPTH_M,
            max_fill_depth_m=MAX_FILL_DEPTH_M,
            workers=WORKERS,
            random_seed=12345,
            clip_to_area=True,
            overwrite=False,
            brandlagen=brandlagen,
        )
        print(resultaat.merged_path)
        print("Tegels met randproblemen:", resultaat.boundary_issue_tile_ids)
