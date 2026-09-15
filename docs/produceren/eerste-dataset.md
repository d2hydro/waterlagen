# Eerste dataset produceren

Dit voorbeeld downloadt AHN-DTM-rastertegels en maakt een VRT waarmee de tegels
als één raster kunnen worden geopend.

```python
from waterlagen.ahn import get_ahn_rasters

vrt_path = get_ahn_rasters(model="dtm", cell_size="05")
print(vrt_path)
```

Beperk een download tot een gebied door `poly_mask` mee te geven. Raadpleeg de
[AHN-bron](../bronnen/ahn.md) voor de gegevens en
[AHN interpoleren](../bewerkingen/ahn-interpoleren.md) voor een vervolgbewerking.
