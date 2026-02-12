## Algemeen
Voor het downloaden van gegevens maken we gebruik van bekende (REST) services op [PDOK](https://www.pdok.nl/). Voor het AHN is er ook een download vanuit de [AHN.nl](https://www.ahn.nl/) beschikbaar.

### AHN
De AHN-download haalt DTM/DSM rastertegels binnen op 0.5m of 5m resolutie en zet die lokaal weg. Je krijgt standaard een VRT terug waarmee alle tegels als één raster te openen zijn.

Aanroepen:
```python
from waterlagen.ahn.download import get_ahn_rasters

# Download DTM 0.5m voor heel Nederland (of alleen ontbrekende tegels)
vrt_file = get_ahn_rasters()

# Download DSM 5m, alleen binnen een polygon-masker
vrt_file = get_ahn_rasters(model="dsm", cell_size="5", poly_mask=my_polygon)
```

Voor alle opties zie de [code-referentie](reference/ahn.md#waterlagen.ahn.get_ahn_rasters)
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
