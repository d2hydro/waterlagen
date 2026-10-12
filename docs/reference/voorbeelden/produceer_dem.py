"""Een DEM maken uit eigen AHN-invoer en een gekozen landgebruikuitsnede."""

from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from waterlagen._geopandas import read_file
from waterlagen.administratieve_gebieden import (
    DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
    download_bestuurlijke_gebieden,
)
from waterlagen.ahn import download_ahn
from waterlagen.areas import NAMED_AREAS, NAMED_AREAS_CRS
from waterlagen.datastore import DataStore
from waterlagen.dem import DemConfig, bouw_dem_tiles
from waterlagen.functioneel_landgebruik.gebouwen import building_paths
from waterlagen.logger import production_logging
from waterlagen.settings import settings

DATA_DIR = Path("data")
AREA = "alkmaar_centrum"
LANDUSE_EXPERIMENT = "experiment_01"  # Voer eerst het landgebruikvoorbeeld uit.
EXPERIMENT = "experiment_01"  # Nieuwe naam bij andere bronnen of rekeninstellingen.
CONFIG = DemConfig(
    interpolation_max_distance_m=250.0,
    building_initial_buffer_m=1.0,
    building_buffer_step_m=1.0,
    building_max_search_distance_m=5.0,
    building_percentile=75.0,
)
WORKERS = 1

if __name__ == "__main__":
    store = DataStore(
        data_dir=DATA_DIR,
        source_data_dir=DATA_DIR / "source_data",
        processed_data_dir=DATA_DIR / "processed_data",
    )
    example_dir = store.processed_data_dir / "voorbeelden" / AREA
    landuse_tile = (
        example_dir
        / LANDUSE_EXPERIMENT
        / "functioneel_landgebruik"
        / "functioneel_landgebruik.tif"
    )

    with production_logging():
        # 1. Gebruik een landgebruikuitsnede met bronraster, gebouw-ID's en pandgeometrieën.
        # De resolutie en pixeluitlijning moeten overeenkomen met het originele AHN.
        _, gebouwen_path = building_paths(landuse_tile)
        gebouwen = read_file(gebouwen_path, layer="gebouwen").to_crs(settings.crs)
        gebied = (
            gpd.GeoSeries([NAMED_AREAS[AREA]], crs=NAMED_AREAS_CRS)
            .to_crs(settings.crs)
            .iloc[0]
        )
        context = gebied
        if not gebouwen.empty:
            context = context.union(box(*gebouwen.total_bounds))
        context = context.buffer(
            max(
                CONFIG.interpolation_max_distance_m,
                CONFIG.building_max_search_distance_m,
            )
        )

        # 2. Haal AHN op voor de uitsnede, volledige panden en zoekafstanden.
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
        landsgrens = download_bestuurlijke_gebieden(
            year=DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
            download_dir=store.administratieve_gebieden_dir,
            overwrite=False,
        )

        # 3. Bereken met de instellingen bovenaan. Eigen AHN? Geef hier het VRT-pad op.
        resultaat = bouw_dem_tiles(
            example_dir / EXPERIMENT / "dem",
            ahn_vrt_path=ahn,
            landuse_tiles=[landuse_tile],
            config=CONFIG,
            workers=WORKERS,
            building_workers=WORKERS,
            landgebied_path=landsgrens.target_path,
            overwrite=False,
        )
        print(resultaat)
