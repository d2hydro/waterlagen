# Eerste dataset produceren

Dit voorbeeld downloadt AHN-DTM-rastertegels voor een klein gebied en maakt
een VRT waarmee de tegels als één raster kunnen worden geopend.

```python
from shapely.geometry import box

from waterlagen.ahn import download_ahn

# Werkgebied in RD New-coördinaten (EPSG:28992), in meters.
poly_mask = box(120_000, 480_000, 121_000, 481_000)

vrt_path = download_ahn(
    poly_mask=poly_mask,
    model="dtm",
    cell_size="05",
)
print(vrt_path)
```

`box` gebruikt de volgorde `xmin, ymin, xmax, ymax`. Pas de coördinaten aan
voor uw werkgebied. Alle AHN-tegels die het masker raken worden volledig
gedownload; het masker knipt de rasters niet af.

Raadpleeg de [AHN-bron](../bronnen/ahn.md) voor de gegevens en
[AHN interpoleren](../bewerkingen/ahn-interpoleren.md) voor een vervolgbewerking.
