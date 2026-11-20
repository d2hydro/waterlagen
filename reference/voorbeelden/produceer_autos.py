"""autos verdelen en het resultaat zelf verder gebruiken."""

from pathlib import Path

import geopandas as gpd

from waterlagen._geopandas import read_file
from waterlagen.administratieve_gebieden import download_wijk_buurtkaart_2025
from waterlagen.areas import NAMED_AREAS, NAMED_AREAS_CRS
from waterlagen.bag import download_bag_light
from waterlagen.cbs import download_buurtgegevens_2025
from waterlagen.datastore import DataStore
from waterlagen.autos import bereken_personenautos_per_vbo
from waterlagen.logger import production_logging
from waterlagen.vbo_buurt import bouw_vbo_buurt, sorteer_op_hilbert

# Instellingen: kies eigen bronpaden in de downloadstappen of hergebruik deze cache.
DATA_DIR = Path("data")
AREA = "alkmaar_centrum"
EXPERIMENT = "experiment_01"  # Kies een nieuwe naam voor een andere proef.
HERBOUW_VOORBEREIDING = False  # True na het vervangen van BAG/CBS-bronnen.

if __name__ == "__main__":
    store = DataStore(
        data_dir=DATA_DIR,
        source_data_dir=DATA_DIR / "source_data",
        processed_data_dir=DATA_DIR / "processed_data",
    )
    output_dir = store.processed_data_dir / "voorbeelden" / AREA / EXPERIMENT
    target = output_dir / "autos.gpkg"
    if target.exists():
        raise FileExistsError(f"Kies een nieuwe experimentnaam: {target} bestaat al")

    with production_logging():
        # 1. Bronnen ophalen; deze downloads en de koppeling zijn landelijk.
        bag = download_bag_light(download_dir=store.bag_dir, overwrite=False)
        kaart = download_wijk_buurtkaart_2025(
            download_dir=store.administratieve_gebieden_dir, overwrite=False
        )
        cijfers = download_buurtgegevens_2025(
            download_dir=store.cbs_dir, overwrite=False
        )
        koppeling = bouw_vbo_buurt(
            bag_path=bag,
            buurtkaart_path=kaart.target_path,
            cbs_buurtgegevens_path=cijfers.target_path,
            bag_vbo_path=store.bag_vbo_path,
            cbs_buurt_path=store.cbs_buurt_path,
            overwrite=HERBOUW_VOORBEREIDING,
        )

        # 2. Kies complete buurten en behoud ALLE bijbehorende woon-VBO's.
        buurten = read_file(koppeling.cbs_buurt_path, layer="cbs_buurt")
        gebied = (
            gpd.GeoSeries([NAMED_AREAS[AREA]], crs=NAMED_AREAS_CRS)
            .to_crs(buurten.crs)
            .iloc[0]
        )
        buurten = buurten.loc[
            buurten.intersects(gebied) & ~buurten.touches(gebied)
        ].copy()
        if buurten.empty:
            raise ValueError("Geen CBS-buurten in het gekozen gebied")
        vbos = read_file(koppeling.bag_vbo_path, layer="bag_vbo")
        vbos = sorteer_op_hilbert(
            vbos.loc[vbos.buurtcode.isin(buurten.buurtcode)].copy()
        )

        # 3. Bereken met GeoDataFrames; resultaat is beschikbaar voor eigen analyses.
        resultaat, ontbrekende_waarden, ongecontroleerde_buurten = (
            bereken_personenautos_per_vbo(vbos, buurten)
        )
        print(resultaat.head())
        print(f"VBO's met ontbrekende CBS-waarden: {ontbrekende_waarden}")
        print(f"Buurten zonder somcontrole: {ongecontroleerde_buurten}")

        # 4. Voeg hier eigen analyses toe. Schrijf daarna het gekozen resultaat.
        output_dir.mkdir(parents=True, exist_ok=True)
        tijdelijk = target.with_name("autos.tmp.gpkg")
        resultaat.to_file(tijdelijk, layer="autos", driver="GPKG", index=False)
        tijdelijk.replace(target)
        print(target)
