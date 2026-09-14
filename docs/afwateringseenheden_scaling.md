# Tegelgrootte en parallelisatie van afwateringseenheden

## Meetopzet

Vervolgbenchmark van 10 september 2026, met de bestaande coverage-definitie
`union(full_extent_of_each_source_tif)`. De productiecode is niet aangepast.
De tijdelijke scripts `scripts/benchmark_afwateringseenheden_scaling.py` en
`scripts/analyze_afwateringseenheden_scaling.py` bewaren hun meetgegevens onder
`data/benchmark_afwateringseenheden_scaling/`.

Gemeenschappelijk centrum: **(168000, 406500)**, EPSG:28992. Dit is het volledig
gedekte kandidaatcentrum het dichtst bij het geometrische zwaartepunt van de
lokale hydroobjectsegmenten, op een zoekgrid met stappen van 1000 m. Het is een
geografisch gemotiveerde keuze, geen bewijs van statistische representativiteit
voor alle terreintypen of waterschappen.

Vooraf zijn zowel de vereniging van de TIFF-rechthoeken als de daadwerkelijke
coverage-maskers op het 2 m doelgrid gecontroleerd. Alle drie maskers zijn
volledig True. De VRT bevat 121 TIFFs.

| Kern | Gebufferde bounds | Grid | Cellen | Coverage | TIFFs met overlap | Segmentfeatures |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 5 km | (163500, 402000, 172500, 411000) | 4500 × 4500 | 20.250.000 | 100% | 6 | 640 |
| 10 km | (161000, 399500, 175000, 413500) | 7000 × 7000 | 49.000.000 | 100% | 12 | 1436 |
| 20 km | (156000, 394500, 180000, 418500) | 12000 × 12000 | 144.000.000 | 100% | 20 | 4441 |

Instellingen: buffer 2000 m, resolutie 2 m, burn depth 100 m, max fill depth
50 m, engine PCRaster, `overwrite=True` en een unieke uitvoermap per job.
Downloads en het opbouwen van het watersysteem zijn uitgesloten; de bestaande
lokale VRT en GeoPackage worden gedeeld als alleen-lezen bronbestanden.

Windows 11, Python 3.14.7, Rasterio 1.5.1, GDAL 3.13.3, PCRaster 4.4.3.
De machine heeft 16 fysieke en 32 logische cores en 66,21 GB RAM; bij de
dekkingscontrole was 51,04 GB beschikbaar. Alle GB zijn decimaal.

De seriële meetreeks gebruikt één spawn-worker met achtereenvolgens twee runs
van 5, 10 en 20 km. Zo blijven Python-imports en de extent-cache bij herhaling
beschikbaar. Windows-bestandscaches worden niet geleegd: eerste/tweede run is
geen gecontroleerde vergelijking tussen koude en warme SSD-cache.

De bestaande volledige tegelworkflow wordt gemeten, inclusief rastervoorbereiding,
PCRaster, polygoniseren, bufferrandcontrole, clip, dissolve en schrijven. De
aanroepen van `lddcreate` en `subcatchment` hebben elk hun eigen timer. Alleen de
korte rastervoorbereidingsfunctie wordt op regelniveau gevolgd om de NumPy-burn
te isoleren. De parent bemonstert elke 100 ms het procesgeheugen, CPU-tijd,
threadaantal en I/O, ook wanneer native code de GIL vasthoudt.

Per-job RSS wordt uit de samples binnen het jobtijdvak afgeleid. Windows
`peak_wset` wordt ook bewaard, maar is cumulatief voor de levensduur van een
worker. Voor gelijktijdige jobs is totaal-RAM het maximum van de gelijktijdige
som van parent- en worker-RSS, niet de som van afzonderlijke pieken op
verschillende tijdstippen. Gedeelde pagina's kunnen daarbij dubbel worden
geteld. CPU-seconden en wall-clockseconden worden afzonderlijk gerapporteerd.
Proces-I/O betreft logische bytes; systeemschijf-I/O omvat ook andere processen.

## Referentie: functioneel landgebruik

`src/waterlagen/functioneel_landgebruik/parallel.py` gebruikt
`ProcessPoolExecutor(max_workers=worker_count)` en `as_completed`. Elke tegel
wordt een bevroren `FunctioneelLandgebruikTileJob` met bounds, bronpaden,
laagnamen, CRS, resolutie, uitvoerconfiguratie en een uniek doelpad. De top-level
functie `_build_tile_worker` roept de bestaande bouwfunctie aan en retourneert
een `Path`. Er worden geen open datasets of volledige arrays naar workers
gestuurd. Bronvalidatie en eventuele downloads gebeuren vooraf in de parent;
workers downloaden niets.

Bronlagen worden in de worker via `waterlagen._geopandas.read_file` geopend;
het uitvoerraster wordt daar met `rasterio.open` geopend. Elke worker schrijft
via een uniek tijdelijk bestand naast zijn doelbestand en vervangt dat doel
na afloop. De parent verzamelt succesvolle paden in de oorspronkelijke
tegelvolgorde. Exceptions van `future.result()` worden per tile-ID vastgelegd;
na afhandeling van de jobs volgt een gezamenlijke `TileBuildError`. De
voortgangsbalk en voltooiings-/foutmeldingen worden door de parent beheerd.

Er is al een expliciete `workers`-parameter. De bibliotheekdefault is
`min(4, os.cpu_count() or 1)`; het workflow-script begrenst standaard op drie.
Deze defaults houden geen rekening met RAM. Logging wordt in het script
geconfigureerd. Er is geen pool-initializer of `QueueHandler`/`QueueListener`
voor workerlogs. Bij Windows spawn erft een worker die parentconfiguratie niet
automatisch; centrale INFO-logging vanuit workers is dus niet geregeld.

## PCRaster, GDAL en procesisolatie

De lokale PCRaster-wrapper gebruikt een runtime-stack via `_pcraster._rte()`;
de pipeline stelt per job de globale clone en opties `unittrue` en `lddin` in.
Dit is een reden om onafhankelijke jobs in aparte processen uit te voeren.
Een threadpool rond verschillende clones is hier niet als veilig aangetoond.

De officiële multicorelijst bevat vooral lokale en focale operaties en noemt
`lddcreate` niet. Het activeren van `PCRASTER_NR_WORKER_THREADS` schakelt in de
geïnstalleerde `__init__.py` bovendien alternatieve operaties in; dat is geen
algemene versnelling van de klassieke LDD-aanroep. Daarom blijft de klassieke
PCRaster-implementatie in deze proef behouden.
[PCRaster multicore-documentatie](https://pcraster.geo.uu.nl/pcraster/4.4.2/documentation/pcraster_project/multicore.html).

Procesisolatie is ook een bekend PCRaster-patroon: het Monte Carlo-framework
kan samples in eigen processen draaien, maar zijn `setForkSamples` ondersteunt
Windows niet. Voor deze Windows-pipeline gebruiken we expliciet Python spawn,
een top-level worker, serialiseerbare jobs, `freeze_support()` en een
`if __name__ == "__main__"`-guard.
[PCRaster framework](https://pcraster.geo.uu.nl/pcraster/4.4.2/documentation/python_modelling_framework/PCRasterPythonFramework.html).

Rasterio-datasets mogen niet tussen processen worden gedeeld. Elke worker
opent de VRT, GeoPackages en eigen rasters opnieuw. Spawn voorkomt ook het
overnemen van GDAL-mutexen en filehandles via fork na GDAL-initialisatie.
[Rasterio concurrency](https://rasterio.readthedocs.io/en/stable/topics/concurrency.html),
[GDAL multiprocessing](https://gdal.org/en/stable/user/multithreading.html).

VRT-readers kunnen sinds GDAL 3.10 zelf meerdere threads gebruiken, standaard
`ALL_CPUS` voor ondersteunde reads. Meer Python-workers kan dus native
oversubscription veroorzaken. `GDAL_NUM_THREADS` en `VRT_NUM_THREADS` moeten
bij een productiepool expliciet worden begrensd. De GDAL-blockcache is per
proces; de standaardlimiet is 5% van RAM en mag bij veel workers niet zonder
meer als gedeelde cache worden beschouwd.
[VRT threading](https://gdal.org/en/stable/drivers/raster/vrt.html#multi-threading-optimizations),
[GDAL cacheconfiguratie](https://gdal.org/en/stable/user/configoptions.html#performance-and-caching).

## Interpretatie voor een heel domein

Voor kernzijde `s` in km en buffer `b = 2 km` geldt:

```text
processed_area = (s + 4)^2
retained_area = s^2
overhead_factor = processed_area / retained_area
tiles = domain_area / retained_area
serial_wall = tiles * mean_tile_wall
cpu_work = tiles * mean_tile_cpu
parallel_wall ≈ serial_wall / measured_speedup
```

Het rekenvoorbeeld gebruikt een vierkant domein van 100 × 100 km, dus
10.000 km². Dat is exact deelbaar door alle drie kernmaten. Werkelijke
waterschapsgrenzen vragen extra randtegels en een gezamenlijke eindmerge;
deze zijn niet door dit ideale oppervlaktemodel gedekt. De empirische
LDD-fit over drie geneste gebieden beschrijft deze locatie en parameters,
geen universele complexiteitswet: reliëf, depressies en netwerkdichtheid
veranderen mee met het gebied.
