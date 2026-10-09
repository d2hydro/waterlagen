# Waterlagen in eigen Python-code

De productiecommando's roepen dezelfde Python-functies aan als onderstaande
voorbeelden. Importeer functies uit `waterlagen`, niet uit `scripts`.
De [productie-API](productie.md) beschrijft de argumenten. Voor de betekenis van
bronnen en resultaten zijn [Bronnen](../bronnen/index.md) en
[Bewerkingen](../bewerkingen/index.md) de ingang.

## Een product maken

```python
from pathlib import Path

from waterlagen.autos.productie import main as produceer_autos
from waterlagen.datastore import DataStore
from waterlagen.logger import production_logging


def main():
    store = DataStore(data_dir=Path("data"))
    with production_logging():
        result = produceer_autos(store, area="alkmaar", run_id="proef")
    return result


if __name__ == "__main__":
    main()
```

Gebruik de `__main__`-guard bij workflows die werkprocessen starten, zeker op
Windows. Zonder `production_logging()` configureert de package geen handlers:
de aanroepende toepassing beheert dan zelf de logging. Met de contextmanager
krijgt u dezelfde centrale logging als de CLI, inclusief geneste producties en
werkprocessen. Na afloop wordt de eerdere loggingconfiguratie hersteld.

De andere productie-ingangen zijn:

```python
from waterlagen.inwoners.productie import main as produceer_inwoners
from waterlagen.afwateringseenheden.productie import main as produceer_afwateringseenheden
from waterlagen.functioneel_landgebruik.productie import main as produceer_landgebruik
from waterlagen.dem.workflow import main as produceer_dem
```

Bijvoorbeeld binnen `main()` uit het eerste voorbeeld:

```python
result = produceer_dem(data_store=store, area="38", run_id="dem_proef", workers=2)
```

Alle ingangen delen `area`, `run_id`, `resume`, `overwrite`, `refresh_sources` en
`offline`. Zie [productiecommando's](../produceren/cli.md) voor hun betekenis.
`workers` is beschikbaar voor de drie raster-/tegelworkflows.
Gebruik `DemConfig` voor DEM-rekeninstellingen.

## Losse bronnen en bewerkingen

De bestaande download- en verwerkingsfuncties blijven beschikbaar. Bij een
volledige productie hoeft u deze niet afzonderlijk aan te roepen.

```python
from waterlagen.bag import download_bag_light
from waterlagen.datastore import DataStore
from waterlagen.liwo import FILENAME, download_raster, polygonize_selected

store = DataStore()
bag = download_bag_light(download_dir=store.bag_dir, overwrite=False)
raster = download_raster(store.source_data_dir / "liwo" / FILENAME)
polygonen = polygonize_selected(
    raster,
    store.source_data_dir / "liwo" / "buitendijks_gebied_uit_liwo.gpkg",
)
```

Voor reeds gedownloade BGT GML Light-ZIP:

```python
from waterlagen.bgt.productie import main as bereid_bgt_voor

# Binnen een main-functie met __main__-guard:
bgt = bereid_bgt_voor(store, workers=2)
```

Een DGM1-gebied moet het ingestelde project-CRS gebruiken:

```python
from waterlagen._geopandas import read_file
from waterlagen.dgm1 import download_dgm1
from waterlagen.settings import settings

gebied = read_file("gebied.gpkg").to_crs(settings.crs).geometry.make_valid().union_all()
vrt = download_dgm1(poly_mask=gebied)
```

Raadpleeg de modulepagina's in deze API-referentie voor overige bronnen en
lagere verwerkingsfuncties. Die functies houden hun eigen cache- en
overschrijfargumenten; de gedeelde runconventie geldt voor de productie-ingangen.

## Verdelingen controleren

```python
from pathlib import Path
from waterlagen.datastore import DataStore
from waterlagen.vbo_buurt.statistiek import lees_verdelingstatistieken

store = DataStore()
root = store.processed_data_dir
statistiek = lees_verdelingstatistieken(
    store,
    inwoners_path=root / "inwoners/nederland/proef/inwoners.gpkg",
    autos_path=root / "autos/nederland/proef/autos.gpkg",
)
```

Dit voorbeeld vergelijkt landelijke CBS-totalen met landelijke uitvoer.
Voor een regionale vergelijking gebruikt u dezelfde buurtcontext als de
productie; de standaardstatistiek leest het landelijke `store.cbs_buurt_path`
en mag daarom niet rechtstreeks als sluitende regiocontrole worden gebruikt.

## BAG-controle

```python
from waterlagen.functioneel_landgebruik.controle import main as controleer_bag

controle = controleer_bag(store, stap=6, overwrite=True)
```

Deze controle gebruikt bestaande bronnen en schrijft de vaste voorbeelden.
Met `bounds` kiest u een andere uitsnede. De vaste gemaalcontrole is beschikbaar
als `waterlagen.functioneel_landgebruik.controle_gemalen.main`.
