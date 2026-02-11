## Bewerkingen

### AHN
Na een AHN‑download werk je verder met de lokale rastertegels (of de VRT). De downloadfunctie levert direct de data die je in bewerkingen nodig hebt. Voor het downloaden van het ahn, en het verkrijgen van de `vrt_file` hieronder zie [Downloads](downloads.md#ahn)

Interpoleren (gaten opvullen) van AHN‑tegels kan direct op een VRT. Je krijgt een nieuwe set GeoTIFFs terug, optioneel weer als VRT.

Aanroepen:
```python
from waterlagen.ahn.interpolate import interpolate_ahn_tiles

filled_vrt_or_dir = interpolate_ahn_tiles(
    ahn_vrt_file=vrt_file,
    max_search_distance=100,
    dir_name="ahn_filled",
)
```

### BAG
BAG‑bewerkingen starten doorgaans vanuit een GeoDataFrame. Die haal je met één van de downloadopties op. Voor het ophalen van BAG-panden en het vekrijgen van `bag_gdf` en de `vrt_file` zie [downloads](downloads.md)

Rasterize (pand‑hoogtekaart) zet BAG‑polygons om naar een raster op basis van een DEM. Dit levert een GeoTIFF met vloerpeilen op.

Aanroepen:
```python
from waterlagen.bag.rasterize import rasterize_bag
from waterlagen import datastore

bag_pand_tif = datastore.processed_data_dir.joinpath("bag_pand.tif")
rasterize_bag(
    dem_raster=vrt_file,
    bag_gdf=bag_gdf,
    bag_pand_tif=bag_pand_tif,
    buffer_step_m=1,
)
```