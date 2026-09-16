## Algemeen
Voor het downloaden van gegevens maken we gebruik van bekende (REST) services op [PDOK](https://www.pdok.nl/). Voor het AHN is er ook een download vanuit de [AHN.nl](https://www.ahn.nl/) beschikbaar.

### AHN
De AHN-download haalt DTM/DSM rastertegels binnen op 0.5m of 5m resolutie en zet die lokaal weg. Je krijgt standaard een VRT terug waarmee alle tegels als één raster te openen zijn.

Voor de landelijke vooraf samengestelde BGT-download gebruikt `download_bgt()` standaard
`datastore.bgt_dir / "bgt-gmllight-nl-nopbp.zip"` als lokale ZIP-cache. Een bestaande
geldige ZIP wordt opnieuw gebruikt; een ontbrekende of corrupte ZIP wordt eerst naar
een tijdelijk bestand gedownload en pas na validatie vervangen. `overwrite=False`
blijft alleen gelden voor de doel-GeoPackage: als die al bestaat, wordt de ZIP-cache
niet opnieuw gedownload.

Aanroepen:
```python
from waterlagen.ahn.download import get_ahn_rasters

# Download DTM 0.5m voor heel Nederland (of alleen ontbrekende tegels)
vrt_file = get_ahn_rasters()

# Download DSM 5m, alleen binnen een polygon-masker
vrt_file = get_ahn_rasters(model="dsm", cell_size="5", poly_mask=my_polygon)
```

Voor alle opties zie de [code-referentie](reference/ahn.md#waterlagen.ahn.get_ahn_rasters)

### DGM1 Nordrhein-Westfalen

DGM1 kun je net als AHN downloaden op basis van een gebied of tegel-ID:

```python
from waterlagen.dgm1 import download_dgm1, get_tiles_features

# my_polygon staat in settings.crs (standaard EPSG:28992).
vrt_file = download_dgm1(poly_mask=my_polygon, missing_only=True)

# Of selecteer expliciet een 1×1 km-tegel uit de NRW-index.
vrt_file = download_dgm1(select_indices=["32_288_5736"])
```

`get_tiles_features(poly_mask=my_polygon)` toont de geselecteerde tegels vóór
download. De functie leest de actuele [NRW-bestandsindex](https://www.opengeodata.nrw.de/produkte/geobasis/hm/dgm1_tiff/dgm1_tiff/)
en kiest per tegel het nieuwste vermelde jaar. Het masker wordt naar UTM32
omgerekend voor de selectie. Geef ook de benodigde rekenbuffers mee in je masker;
de downloader voegt zelf geen buffer toe.

De download schrijft naar `datastore.dgm1_dir` (`source_data/dgm1_nrw`).
Standaard krijg je `dgm1_nrw.vrt` terug met uitsluitend de geselecteerde tegels.
Met `create_vrt=False` krijg je de downloadmap terug. Een bestaande VRT wordt
pas vervangen nadat alle geselecteerde downloads zijn geslaagd. Oudere of
niet-geselecteerde TIFF-bestanden blijven op schijf staan.

Gebruik vanuit de terminal een vectorbestand als masker:

```powershell
pixi run --environment afwateringseenheden python scripts/download_dgm1_nrw.py --mask gebied.gpkg --layer gebied
```

In VS Code kun je bovenaan het script **Run Cell** gebruiken bij `# %%`.
Gebruik de omgeving `afwateringseenheden` en de repository als werkmap.
Vul `MASK_PATH` en eventueel `MASK_LAYER` in; de cel leest geen Jupyter-argumenten.
Een bestaande URL-lijst blijft ook bruikbaar, zonder de online index te lezen:

```python
from pathlib import Path
from waterlagen.dgm1 import download_dgm1

vrt_file = download_dgm1(url_list=Path("urls.txt"))
```

Voor Run Cell stel je `MASK_PATH` of `URL_LIST` in. Zonder selectie geeft het
script een duidelijke foutmelding; er is geen lokale lijst meegeleverd.
De pakketfunctie vereist een masker, tegel-ID's of URL-lijst en start geen
onbegrensde download van heel NRW.

Standaard worden vier bestanden tegelijk gedownload, met drie pogingen per
tegel en een HTTP-timeout van 60 seconden. Dit is instelbaar via `workers`,
`retries` en `timeout`. Geldige bestaande bestanden worden hergebruikt met
`missing_only=True`; `missing_only=False` downloadt de selectie opnieuw.
Een bestaand bestand wordt pas vervangen na een geslaagde download en controle.
De bestanden blijven in hun oorspronkelijke coördinatenstelsel (UTM32) en
hoogtestelsel (DHHN2016); omzetting naar RD/NAP gebeurt hier nog niet.
Het script voor [afwateringseenheden](reference/afwateringseenheden.md#duits-dem-langs-de-grens)
maakt daarvan aparte RD/NAP-tegels en gebruikt deze waar AHN ontbreekt.

Zie de [DGM1-code-referentie](reference/dgm1.md) voor alle parameters.

### BAG
Voor BAG kun je óf direct via WFS downloaden (met bbox‑filter), óf de landelijke "bag‑light" GeoPackage ophalen en daaruit selecteren.

Aanroepen:
```python
from waterlagen.bag.download import download_bag_light, get_bag_features

# Download de landelijke bag-light.gpkg
bag_gpkg = download_bag_light()

# Download BAG features binnen bbox via WFS
bag_gdf = get_bag_features(bbox, layer="pand", source="wfs")

# Of lezen uit bag-light
bag_gdf = get_bag_features(bbox, layer="pand", source="bag-light")
```
Voor alle opties zie de [code-referentie](reference/bag.md#waterlagen.bag.get_bag_features)

### BGT
De BGT‑download werkt in drie stappen: request indienen, status pollen, en het resultaat als GeoPackages opslaan. Met `get_bgt_features` gebeurt dit in één call.

Aanroepen:
```python
from waterlagen.bgt.download import get_bgt_features
from waterlagen import datastore

# Download enkele featuretypes binnen een polygon of bbox
out_dir = get_bgt_features(
    featuretypes=["waterdeel", "pand"],
    poly_mask=my_polygon_or_bbox,
    download_dir=datastore.bgt_dir,
)
```

Voor alle opties zie de [code-referentie](reference/bgt.md#waterlagen.bgt.get_bgt_features)

### HYDAMO
De landelijke GKW HYDAMO GeoPackage wordt als ZIP aangeboden. `download_hydamo()`
downloadt het archief tijdelijk, valideert de GeoPackage daarin en schrijft het
resultaat atomair naar `datastore.hydamo_dir / "hydamo.gpkg"`. Met
`overwrite=False` wordt een bestaand doelbestand opnieuw gebruikt.

```python
from waterlagen.hydamo import download_hydamo

hydamo = download_hydamo()
```

Voor alle opties zie de [code-referentie](reference/hydamo.md#waterlagen.hydamo.download_hydamo).

### Administratieve gebieden
Bestuurlijke gebieden en waterschapsgrenzen worden als GeoPackages in
`datastore.administratieve_gebieden_dir` opgeslagen. Bestuurlijke gebieden zijn
jaargangen: geef daarom altijd expliciet een jaar op. De tile-workflow gebruikt
standaard jaargang 2026 en leest de landsgrens uit de laag `landgebied`; download
deze bron vooraf met `download_bestuurlijke_gebieden(year=2026)`.

```python
from waterlagen.administratieve_gebieden import (
    download_bestuurlijke_gebieden,
    download_waterschapsgrenzen,
)

bestuurlijke_gebieden = download_bestuurlijke_gebieden(year=2026)
waterschapsgrenzen = download_waterschapsgrenzen()
```

De genormaliseerde GeoDataFrames bevatten `naam`, `bgt_code`,
`waterbeheercode`, `bron`, `versie` en `geometry`, naast relevante oorspronkelijke
bronvelden. `bgt_code` komt uit het bronveld `code`; `waterbeheercode` komt uit
`waterbeheerdercode`. Ontbreekt die laatste waarde, dan wordt uitsluitend een code
uit `nen3610id` in de vorm `NL.WBHCODE.<code>.<type>.<id>` gebruikt. Een mislukte
fallback blijft leeg en geeft een waarschuwing.

Voor alle opties zie de [code-referentie](reference/administratieve_gebieden.md).
