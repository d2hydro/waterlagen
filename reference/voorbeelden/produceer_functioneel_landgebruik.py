"""Een instelbare uitsnede van functioneel landgebruik maken, inclusief gebouwen."""

from pathlib import Path

import geopandas as gpd

from waterlagen.administratieve_gebieden import (
    DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
    download_bestuurlijke_gebieden,
)
from waterlagen.areas import NAMED_AREAS, NAMED_AREAS_CRS
from waterlagen.bag import download_bag_light
from waterlagen.bgt import download_bgt
from waterlagen.brp import download_brp
from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik import (
    FunctioneelLandgebruikSources,
    bouw_functioneel_landgebruik,
)
from waterlagen.functioneel_landgebruik.gebouwen import ensure_building_index
from waterlagen.functioneel_landgebruik.osm_drinkwater import download_osm_drinkwater
from waterlagen.hydamo import download_hydamo
from waterlagen.liwo import FILENAME, download_raster, polygonize_selected
from waterlagen.logger import production_logging
from waterlagen.settings import settings
from waterlagen.top10nl import download_top10nl
from waterlagen.waterketen_damo import download_waterketen_damo

DATA_DIR = Path("data")
AREA = "alkmaar_centrum"
EXPERIMENT = "experiment_01"  # Nieuwe naam bij andere bronnen of instellingen.
RESOLUTION_M = 0.5  # Houd 0.5 aan als deze uitsnede daarna naar het DEM gaat.
GAP_FILL_DISTANCE_M = 1.0
BUILDING_CONTEXT_M = 5.0  # Minstens de maximale gebouwzoekafstand van het DEM.
MAPPING_CSV = None  # Of Path("mijn_landgebruik.csv"), met het bestaande tabelschema.
BGT_FEATURES = (
    "waterdeel",
    "ondersteunendwaterdeel",
    "wegdeel",
    "ondersteunendwegdeel",
    "begroeidterreindeel",
    "onbegroeidterreindeel",
)

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
        / "functioneel_landgebruik"
    )
    gebied = (
        gpd.GeoSeries([NAMED_AREAS[AREA]], crs=NAMED_AREAS_CRS)
        .to_crs(settings.crs)
        .iloc[0]
    )

    with production_logging():
        # 1. Bronnen ophalen/hergebruiken. Dit zijn landelijke downloads!
        # Vervang een downloadaanroep door een eigen Path om lokale invoer te kiezen.
        bag = download_bag_light(download_dir=store.bag_dir, overwrite=False)
        bgt = download_bgt(
            download_dir=store.bgt_dir,
            target_path=store.bgt_dir / "voorbeeld_landgebruik.gpkg",
            featuretypes=BGT_FEATURES,
            overwrite=False,
        )
        brp = download_brp(
            download_dir=store.brp_dir, filename="brp.gpkg", overwrite=False
        )
        top10nl = download_top10nl(download_dir=store.top10nl_dir, overwrite=False)
        liwo = download_raster(
            store.source_data_dir / "liwo" / FILENAME, overwrite=False
        )
        hydamo = download_hydamo(download_dir=store.hydamo_dir, overwrite=False)
        waterketen = download_waterketen_damo(
            download_dir=store.waterketen_damo_dir, overwrite=False
        )
        drinkwater = download_osm_drinkwater(data_store=store, overwrite=False)
        landsgrens = download_bestuurlijke_gebieden(
            year=DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
            download_dir=store.administratieve_gebieden_dir,
            overwrite=False,
        )

        # 2. Maak de LIWO-vlakken en een herbruikbare koppeling van BAG-ID's.
        buitendijks = output_dir / "buitendijks.gpkg"
        if not buitendijks.exists():
            polygonize_selected(liwo, buitendijks)
        gebouw_index = ensure_building_index(bag, output_dir / "gebouw_index.sqlite")

        # 3. Kies expliciet de invoer. Eigen bestanden moeten dezelfde lagen/velden hebben.
        sources = FunctioneelLandgebruikSources(
            bag_gpkg=bag,
            bgt_gpkg=bgt.target_path,
            brp_gpkg=brp.path,
            top10nl_gpkg=top10nl,
            buitendijks_gpkg=buitendijks,
            gemalen_gpkg=hydamo.target_path,
            rwzi_gpkg=waterketen.target_path,
            drinking_water_gpkg=drinkwater,
        )

        # 4. Bereken precies deze rechthoek; de bronvoorbereiding gebruikt ook de omgeving.
        resultaat = bouw_functioneel_landgebruik(
            output_dir / "functioneel_landgebruik.tif",
            bounds=gebied.bounds,
            crs=settings.crs,
            resolution_m=RESOLUTION_M,
            gap_fill_distance_m=GAP_FILL_DISTANCE_M,
            sources=sources,
            landgebied_path=landsgrens.target_path,
            mapping_csv=MAPPING_CSV,
            building_index_path=gebouw_index,
            building_context_m=BUILDING_CONTEXT_M,
            diagnostics_path=output_dir / "nodata.gpkg",
            download_missing_sources=False,
            overwrite=False,
        )
        print(resultaat)
