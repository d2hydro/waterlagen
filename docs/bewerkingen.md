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

### Afwateringseenheden
De eerste stap leest geselecteerde HyDAMO-hydroobjecten en puntobjecten. De
HyDAMO-bronkolom `categorieoppwaterlichaam` bevat onder meer de waarden
`primair` en `secundair`; de alias `categorieoppervlaktewater` is alleen voor
filters beschikbaar. Waterbeheerdercodes worden uit `nen3610id` gelezen.
Primaire hydroobjecten worden eerst gesplitst bij nabijgelegen puntobjecten en
daarna op een maximale lengte. Verbindingen tussen primaire hydroobjecten zijn
tweedimensionale punten tussen finale hydroobjectsegmenten. Ze omvatten zowel
gedeelde segmentuiteinden door knippen op lengte als verbindingen bij relevante
puntobjecten. Per hydraulisch knooppunt met `n` segmenten worden precies
`n - 1` gerichte verbindingen gemaakt: `van_segment` eindigt op het knooppunt
en `naar_segment` begint daar. Bij meerdere in- en uitgaande
segmenten wordt een reproduceerbare hoofdroute op segment-ID gekozen. Een
knoop met alleen in- of alleen uitgaande segmenten gebruikt het laagste
segment-ID als topologische wortel. Een
geometrische kruising zonder gedeeld uiteinde of relevant puntobject vormt geen
verbinding.

Secundaire hydroobjecten worden op hun volledige geometrie gefilterd.
`hydroobject_secundair` bevat alleen secundaire objecten die binnen 2 m van een
primair of ander secundair object liggen; dit geldt zowel bij vertices als
ergens op een lijnsegment. Gebruik `secondary_connection_tolerance` bij
`write_watersysteem()` om deze tolerantie aan te passen.
`hydroobject_secundair_niet_verbonden` bevat de overige geselecteerde objecten.
De twee lagen vormen samen de oorspronkelijke secundaire selectie.
De laag `hydroobject_segment` bevat bovendien een meegeleverde QGIS-stijl in
de GeoPackage-tabel `layer_styles`.

Zonder een expliciet uitvoerpad wordt het bestand `watersysteem.gpkg` onder
`datastore.afwateringseenheden_path` geschreven. Een bestaand resultaat wordt
standaard hergebruikt; zet `overwrite=True` om het opnieuw op te bouwen.

```python
from shapely.geometry import box

from waterlagen import datastore
from waterlagen.afwateringseenheden import (
    prepare_watersysteem,
    read_hydroobjecten,
    read_puntobjecten,
    write_watersysteem,
)

selectie = box(120_000, 410_000, 121_000, 411_000)
hydamo_path = datastore.hydamo_dir / "hydamo.gpkg"
hydroobjecten = read_hydroobjecten(
    hydamo_path,
    spatial_selection=selectie,
    waterbeheercodes=["38"],
)
hydroobject_primair = hydroobjecten.loc[
    hydroobjecten["categorieoppwaterlichaam"] == "primair"
]
hydroobject_secundair = hydroobjecten.loc[
    hydroobjecten["categorieoppwaterlichaam"] == "secundair"
]
puntobjecten = read_puntobjecten(hydamo_path, spatial_selection=selectie)
watersysteem = prepare_watersysteem(
    hydroobject_primair,
    puntobjecten,
    hydroobject_secundair=hydroobject_secundair,
)
watersysteem_path = write_watersysteem(
    hydroobject_primair=hydroobject_primair,
    hydroobject_secundair=hydroobject_secundair,
    watersysteem=watersysteem,
)
```

## Rasters voor afwateringseenheden

`prepare_watersysteem_rasters()` maakt voor een vierkant in het project-CRS
een DEM en een raster met hydroobjectsegment-ID's. Standaard wordt
`source_data/ahn/dtm_05/dtm_05.vrt` op een grid van 2 bij 2 meter gelezen. De
DEM bevat na `rasterio.fill.fillnodata` geen NoData-cellen. Primaire
hydroobjecten worden met tweemaal en secundaire hydroobjecten met eenmaal de opgegeven branddiepte
verlaagd; bij overlap heeft primair voorrang. De bestaande datatype-, schaal-
en offsetmetadata van de AHN-DTM blijven behouden.

```python
from shapely.geometry import box

from waterlagen.afwateringseenheden import prepare_watersysteem_rasters

rasters = prepare_watersysteem_rasters(
    box(190_000, 375_000, 191_000, 376_000),
    burn_depth_m=5.0,
)
```

`calculate_subcatchments()` gebruikt deze twee rasters als in-memory
PCRaster-clone. De LDD en de subcatchments worden als `ldd.tif` en
`subcatchments.tif` naast de voorbereide rasters geschreven. De polygonen
komen in `afwateringseenheden.gpkg` in de map van het vierkant, laag
`afvoergebiedaanvoergebied`; iedere polygoon krijgt na terugkoppeling met
`hydroobject_segment` een `segment_id`.

```python
from waterlagen.afwateringseenheden import calculate_subcatchments

subcatchments = calculate_subcatchments(rasters)
```

Voor grotere gebieden kan dezelfde berekening per tegel worden uitgevoerd.
`calculate_afwateringseenheden_tiles()` maakt per tegel een gebufferde
rekengrid, hergebruikt `prepare_watersysteem_rasters()` en
`calculate_subcatchments()`, knipt bruikbare polygonen terug naar de echte
tegel en schrijft optioneel een samengevoegde GeoPackage. Tegels zonder
hydroobjectsegmenten worden overgeslagen. Als een afwateringseenheid vanaf de
buitenrand van de tegelbuffer tot in de echte tegel reikt, wordt die tegel in
`boundary_issue_tile_ids` gemeld; vergroot dan de `tile_buffer_m` en bereken
die tegel opnieuw.

```python
from waterlagen import datastore
from waterlagen.afwateringseenheden import calculate_afwateringseenheden_tiles

result = calculate_afwateringseenheden_tiles(
    gebied,
    burn_depth_m=100,
    ahn_vrt_path=datastore.ahn_dir / "dtm_05" / "dtm_05.vrt",
    watersysteem_path=datastore.afwateringseenheden_path / "watersysteem.gpkg",
    output_dir=datastore.afwateringseenheden_path / "tiles",
    merged_output_path=datastore.afwateringseenheden_path / "afwateringseenheden.gpkg",
    tile_size_m=5000,
    tile_buffer_m=2000,
)
```
