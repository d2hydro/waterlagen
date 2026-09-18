# DGM1 downloaden

!!! warning "Vereist nieuwere broncode"
    DGM1 is niet beschikbaar in release 2026.2.1 of de bijbehorende
    productie-TOML. Voer deze voorbeelden uit vanuit de broncoderepository
    `waterlagen`, met de [ontwikkelomgeving](../bijdragen/ontwikkelomgeving.md).
    De onderstaande terminalopdracht gebruikt de omgeving `afwateringseenheden`.

Selecteer [DGM1 Nordrhein-Westfalen](../bronnen/dgm1.md) met een gebied,
tegel-ID's of een lokale URL-lijst. Geef ook benodigde rekenbuffers mee;
de downloader voegt zelf geen buffer toe.

## Vanuit Python

```python
from waterlagen.dgm1 import download_dgm1, get_tiles_features

# my_polygon staat in settings.crs (standaard EPSG:28992).
tiles = get_tiles_features(poly_mask=my_polygon)
vrt_file = download_dgm1(poly_mask=my_polygon, missing_only=True)

# Of selecteer expliciet een 1 × 1 km-tegel uit de NRW-index.
vrt_file = download_dgm1(select_indices=["32_288_5736"])
```

`get_tiles_features()` toont de geselecteerde tegels vóór download. Het masker
wordt voor de selectie omgerekend naar UTM32. Een URL-lijst kan worden gebruikt
zonder de online index te lezen:

```python
from pathlib import Path
from waterlagen.dgm1 import download_dgm1

vrt_file = download_dgm1(url_list=Path("urls.txt"))
```

## Vanuit de terminal of VS Code

```powershell
pixi run --environment afwateringseenheden python scripts/download_dgm1_nrw.py --mask gebied.gpkg --layer gebied
```

Gebruik voor **Run Cell** bij `# %%` de omgeving `afwateringseenheden` en de
repository als werkmap. Stel `MASK_PATH` en eventueel `MASK_LAYER` in, of kies
`URL_LIST`. De cel leest geen Jupyter-argumenten. Zonder selectie geeft het
script een foutmelding; er is geen lokale lijst meegeleverd. De pakketfunctie
vereist eveneens een masker, tegel-ID's of URL-lijst en start geen onbegrensde
download van heel NRW.

## Uitvoer en hergebruik

Downloads komen in `datastore.dgm1_dir` (`source_data/dgm1_nrw`). Standaard krijg
je `dgm1_nrw.vrt` terug met uitsluitend de geselecteerde tegels. Met
`create_vrt=False` krijg je de downloadmap terug. Een bestaande VRT wordt pas
vervangen nadat alle geselecteerde downloads zijn geslaagd. Oudere en
niet-geselecteerde TIFF-bestanden blijven op schijf staan.

Standaard worden vier bestanden tegelijk gedownload, met drie pogingen per
tegel en een HTTP-timeout van 60 seconden. Dit is instelbaar via `workers`,
`retries` en `timeout`. Geldige bestaande bestanden worden hergebruikt met
`missing_only=True`; `missing_only=False` download de selectie opnieuw. Een
bestaand bestand wordt pas vervangen na een geslaagde download en controle.

De download zet hoogtes nog niet om naar RD/NAP. Voor een gecombineerd
AHN/DGM1-hoogtemodel gebruikt een eigen workflow
[`prepare_ahn_dgm1_dem()`](../reference/afwateringseenheden.md#waterlagen.afwateringseenheden.dem.prepare_ahn_dgm1_dem).
Deze functie maakt aparte omgerekende tegels en gebruikt DGM1 waar AHN ontbreekt.

Zie de [DGM1-API](../reference/dgm1.md) voor alle downloadparameters.
