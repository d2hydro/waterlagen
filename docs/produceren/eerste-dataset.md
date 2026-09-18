# Eerste dataset produceren

Dit voorbeeld download AHN-DTM-rastertegels voor een klein gebied en maakt
een VRT waarmee de tegels als één raster kunnen worden geopend.

Volg eerst [Installatie](installatie.md). Sla de onderstaande Python-code op als
`eerste_dataset.py` in de Waterlagen-projectmap.

```python
from shapely.geometry import box

from waterlagen.ahn import get_ahn_rasters

# Werkgebied in RD New-coördinaten (EPSG:28992), in meters.
poly_mask = box(120_000, 480_000, 121_000, 481_000)

vrt_path = get_ahn_rasters(
    poly_mask=poly_mask,
    model="dtm",
    cell_size="05",
)
print(vrt_path)
```

Voer het bestand vanuit die projectmap uit:

```console
pixi run --environment afwateringseenheden python eerste_dataset.py
```

Dit start de download. Het pad naar de VRT verschijnt na afloop in de terminal;
open die VRT in QGIS. De downloads komen in de ingestelde
[DataStore](configuratie.md).

`box` gebruikt de volgorde `xmin, ymin, xmax, ymax`. Pas de coördinaten aan
voor uw werkgebied. Alle AHN-tegels die het masker raken worden volledig
gedownload; het masker knipt de rasters niet af.

Raadpleeg de [AHN-bron](../bronnen/ahn.md) voor de gegevens en
[AHN interpoleren](../bewerkingen/ahn-interpoleren.md) voor een vervolgbewerking.
