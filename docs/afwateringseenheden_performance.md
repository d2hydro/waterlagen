# Performanceonderzoek afwateringseenheden

Benchmarkdatum: 10 september 2026. De oorspronkelijke benchmark hieronder
gebruikt productiecode ongewijzigd ten opzichte van commit `4c354c82a94067f95d0478f341b36715189b086b`.

## Afbakening en reproduceerbaarheid

Rekenbounds: `(168000, 358000, 182000, 372000)` in EPSG:28992.
De bestaande Aa-en-Maas-workflow gebruikt een kerntegel van 10 km met een
buffer van 2 km. Daarom is uitsluitend kerntegel
`170000_360000_180000_370000` geselecteerd. Dit levert exact de gevraagde
14 Ã— 14 km rekenbounds op, zonder een extra buffer rond die bounds.
Parameters: resolutie 2 m, burn depth 100 m, max fill depth 50 m,
engine PCRaster, nieuwe output met `overwrite=True`.
Voor deze geÃ¯soleerde proef is `gebied` de kerntegel zelf. De eindclip en
merge betreffen dus Ã©Ã©n tegel, niet de volledige Aa-en-Maas-gebiedsmerge.

De bestaande lokale `dtm_05.vrt` en `watersysteem.gpkg` uit de ingestelde
datastore worden gelezen. Downloads, normaliseren van waterschapsgrenzen
en `prepare_watersysteem()` zijn voorafgaande stappen en zijn niet opnieuw
uitgevoerd. De benchmark schrijft alleen in `data/profiling_afwateringseenheden/`.

Het tijdelijke script `scripts/profile_afwateringseenheden_tile.py` verpakt
functies tijdens dit ene proces met timers. Geselecteerde Python-regels worden
apart getimed, zodat rasterreads, casts en burn-bewerkingen zichtbaar zijn.
Een apart proces bemonstert het werkgeheugen elke 100 ms, ook tijdens native
GDAL/PCRaster-aanroepen. De productiebronbestanden worden niet aangepast.
Verwijderen van het script verwijdert alle instrumentatie.

```powershell
pixi run --environment afwateringseenheden python scripts/profile_afwateringseenheden_tile.py
pixi run --environment afwateringseenheden python scripts/profile_afwateringseenheden_tile.py --mode direct
```

In deze sessie bevatte het geÃ«rfde PATH ook DLL-mappen van de default-omgeving.
Dat veroorzaakte een importfout in `rasterio._warp`. Voor het benchmarkproces
zijn die PATH-items verwijderd voordat bovenstaande pixi-aanroep werd gestart;
er zijn geen pakketten of projectinstellingen gewijzigd om dit op te lossen.

Versies: Python 3.14.7, Rasterio 1.5.1, GDAL 3.13.3, PCRaster 4.4.3;
fysiek RAM 66,21 GB.
Tijden zijn wall-clock, inclusief native aanroepen. Geneste timings mogen
niet bij hun bovenliggende totaal worden opgeteld. Dit is Ã©Ã©n volledige run,
zonder legen van de Windows-bestandscache; geen gecontroleerde cold-cache-test.
Profiling voegt enige overhead toe, vooral bij korte stappen.
I/O-tellers meten proces-I/O inclusief cacheverkeer en een kleine hoeveelheid
profilinglogverkeer, geen fysieke SSD-throughput. RAM-pieken zijn proces-RSS,
inclusief GDAL-cache en bibliotheken; arraygroottes zijn apart berekend.
Alle MB/GB hieronder zijn decimaal.

## Gemeten tijden

Totale tegelworkflow: **1971,965 s (32 min 51,97 s)**. Tijd tot het starten
van `lddcreate`: circa **898,95 s**. De totale procesgeheugenpiek volgens
Windows was **3,236 GB**; deze korte piek trad rond de burn/cast-fase op.
De afzonderlijke RSS-waarden hieronder zijn maxima van de 100 ms-samples
en de functiegrenzen; zeer korte allocatiepieken kunnen daartussen vallen.

`N` betekent **7000 Ã— 7000 cellen op 2 m**. f64/f32 zijn float64/float32;
i16/i32 zijn int16/int32; u8 is uint8. Alle rasterstappen na resampling
blijven op hetzelfde 2 m grid. R/W is gemeten logische proces-I/O in MB.

| Stap | Tijd | Inputgrootte | Outputgrootte | RAM / I-O | Bottleneck? |
| --- | ---: | --- | --- | --- | --- |
| Paden bepalen / VRT openen | 0,003 s openen | VRT met 121 bronnen | Bandhandle; 7 relevante bronnen | 0,054 MB R; bronheaders worden verder lui geopend | Nee |
| DEM-window lezen + virtuele mosaic + bilineaire resampling | 8,110 s | 28000Â² i16 op 0,5 m, deels ongedekt | N f64 | 392 MB doelarray; RSS 1,91 GB; 323,85 MB R | Nr. 3; 0,41% |
| Afzonderlijke merge / CRS-reprojection | Geen aparte stap | VRT, EPSG:28992 | EPSG:28992 | Mosaic en gridmapping inbegrepen in 8,110 s; geen NumPy-merge | Nee |
| `_fill_dem_nodata()` | **889,455 s** | N f64, 44,2% NoData | N f64, gevuld | 392 MB array + 49 MB masker; RSS 2,49 GB; geen data-I/O | **Nr. 2; 45,10%** |
| Drie vectorlagen lezen met bbox | 0,038 s | Watersysteem-GPKG | Drie featureselecties | 1,47 MB R | Nee |
| Maskers en segmenten rasteriseren | 0,139 s | Featureselecties | 2 Ã— N bool + N i32 | 294 MB arrays | Nee |
| Burn-arrays, subtractie en cast | circa 0,23 s | N f64 + maskers | N i16 | Meerdere tijdelijke arrays van 392 MB; hier hoogste RAM-piek | RAM, niet tijd |
| DEM / segmentraster schrijven | 0,085 / 0,182 s | N i16 / N i32 | 47,908 / 0,575 MB TIFF | 98 / 196 MB arrays; 48,60 MB W samen | Nee |
| Rasterpaar valideren | 0,167 s | Twee TIFFs | Metadata + DEM-maskercontrole | Volledige DEM-read; 95,82 MB R | Nee |
| **`prepare_watersysteem_rasters()` totaal** | **898,529 s** | VRT + watersysteem | DEM + segment-TIFF | RSS-samplemax 2,75 GB; 421,35 MB R / 48,64 MB W | Inclusief bovenstaande stappen |
| `_has_segment_cells()` | 0,086 s | N i32 op disk | bool | 196 MB readarray + 49 MB vergelijking; 0,65 MB R | Nee |
| PCRaster-inputreads inclusief casts | 0,105 + 0,082 s | N i16 + N i32 | N f64 + N i32 | 588 MB arrays; circa 48,61 MB R | Nee |
| Twee `numpy2pcr()`-conversies | 0,106 s | N f64 + N i32 | Scalar + Nominal maps | Circa 392 MB extra maps; geen data-I/O | Nee |
| **`lddcreate()`** | **1066,976 s** | N Scalar | N LDD | Circa 49 MB LDD; RSS 1,72 GB; geen data-I/O | **Nr. 1; 54,11%** |
| PCRaster `subcatchment()` | 4,105 s | N LDD + Nominal | N Nominal | Circa 196 MB catchmentmap; RSS 1,50 GB | Klein; 0,21% |
| Twee `pcr2numpy()` + casts | 0,077 s | Twee PCRaster maps | N u8 + N i32 | 245 MB resultaten + tijdelijke kopieÃ«n | Nee |
| LDD / catchments schrijven | 0,149 / 0,125 s | N u8 / N i32 | 15,288 / 0,899 MB TIFF | 16,30 MB W samen | Nee |
| Outputgrid valideren | 0,019 s | Twee TIFFs | Alleen metadata | 0,005 MB R; geen pixelread | Nee |
| Volledige segment-ID-mapping lezen | 0,120 s | Volledige segmentlaag | FID â†’ segment-ID | 11,96 MB R; RSS 0,52 GB | Nee |
| Polygoniseren | 0,972 s | N i32 | 461 polygonen | 196 MB raster + maskers/geometrieÃ«n; RSS 0,83 GB | Nee |
| Tegel-GPKG schrijven / teruglezen | 0,059 s | 461 polygonen | 5,571 MB GPKG | 5,92 MB W / 12,68 MB R | Nee |
| **`calculate_subcatchments()` totaal** | **1072,972 s** | DEM + segment-TIFF | LDD, catchments, polygonen | RSS 1,74 GB; 73,38 MB R / 22,25 MB W | Inclusief PCRaster en output hierboven |
| Bufferrandcontrole / clip | 0,166 s | 461 polygonen | Bruikbare kerntegelpolygonen | RSS 0,26 GB; geen data-I/O | Nee |
| EÃ©n-tegelmerge / eind-GPKG schrijven | 0,173 / 0,036 s | Kerntegelpolygonen | 224 features, 3,154 MB GPKG | RSS 0,27 GB; 3,51 MB W / 2,84 MB R | Nee |

De validatie heeft bevestigd dat alle vier TIFFs exact de gevraagde bounds,
7000 Ã— 7000 cellen en 2 m resolutie hebben. Ze zijn DEFLATE-gecomprimeerd
met **strips van 1 Ã— 7000**, geen tegels. Het bron-DEM is wel getegeld.
De workflow meldt tevens dat de buffer van 2 km mogelijk onvoldoende is;
deze bestaande bufferrandcontrole is niet aangepast of onderdrukt.

Ruwe meetgegevens staan in
`data/profiling_afwateringseenheden/20260910_183254_benchmark/`:
`events.jsonl`, `memory.jsonl`, `metadata.json`, `summary.json`,
`output_metadata.json` en de geÃ¯soleerde uitvoerbestanden.

## Uitgevoerde codepath

1. `scripts/afwateringseenheden_aa_en_maas.py` haalt vooraf AHN en HyDAMO op
   en schrijft het voorbereide watersysteem. `download_ahn()` bouwt met
   `gdal.BuildVRT` een virtuele verwijzing naar de AHN-TIFFs; dit gebeurt vÃ³Ã³r
   de tegelberekening, niet opnieuw binnen elke tegel.
2. `tiles.calculate_afwateringseenheden_tiles()` bepaalt en selecteert de
   kerntegel, maakt de outputmap en bepaalt de gebufferde rekengeometrie.
3. `raster.prepare_watersysteem_rasters()` maakt een `RasterGrid`, bepaalt de
   bronpaden, opent de VRT en roept `_resample_dem()` aan.
4. `_resample_dem()` reserveert een 7000 Ã— 7000 float64-array en gebruikt
   `reproject(source=rasterio.band(source, 1), destination=data, bilinear)`.
   Windowselectie, virtuele mosaic, blokreads en resampling vinden samen in
   GDAL plaats. Er is geen aparte NumPy-merge of zelfstandige bronwindow-read.
5. `_fill_dem_nodata()` maakt een geldigheidsmasker en roept `fillnodata()`
   aan met de volledige rasterdiagonaal als zoekafstand.
6. Drie watersysteemlagen worden met bbox gelezen. Primair/secundair worden
   gerasteriseerd, burn-arrays opgebouwd en het DEM teruggecast naar int16.
   DEM en int32-segmentraster worden als tijdelijke GeoTIFF geschreven.
   `_validate_rasters()` heropent beide en leest het volledige DEM met masker;
   vervolgens worden de tijdelijke bestanden atomair hernoemd.
7. `tiles._has_segment_cells()` leest het volledige segmentraster.
8. `pcraster.calculate_subcatchments()` opent beide rasters opnieuw.
   `_calculate_pcraster_maps()` stelt de clone in, leest het hele DEM,
   cast naar float64, leest/cast het segmentraster naar int32 en doet twee
   `numpy2pcr`-conversies. Daarna volgen `lddcreate`, `subcatchment` en twee
   `pcr2numpy`-conversies met aanvullende NumPy-casts.
9. LDD (uint8) en catchments (int32) worden geschreven en alleen op
   gridmetadata gevalideerd. De volledige segment-ID-laag wordt ingelezen.
   `_polygonize_subcatchments()` doet `unique`, `isin`, `shapes` en maakt
   geometrieÃ«n. De GeoPackage wordt geschreven en volledig teruggelezen
   om het aantal features te controleren.
10. De tegelworkflow controleert bufferranden, knipt bruikbare polygonen op
    de kerntegel, voegt samen met `dissolve` en schrijft de merged GeoPackage.

## Datadekking en rastergroottes

De VRT is 150000 Ã— 170000 cellen. Het gevraagde bronwindow heeft offsets
`(86000, 131000)` en afmetingen 28000 Ã— 28000: **784 miljoen cellen**.
Dat zou volledig gematerialiseerd 1,568 GB int16, 3,136 GB float32 of
6,272 GB float64 zijn. Het doel heeft **49 miljoen cellen**:
98 MB int16, 196 MB int32/float32, 392 MB float64 of 49 MB bool/uint8.

Zeven lokale AHN-TIFFs overlappen het window: M_57EN2, M_57FN1, M_57FN2,
M_57FZ1, M_57FZ2, M_58AN1 en M_58AZ1. Elk is 12500 Ã— 10000 int16,
0,5 m, schaal 0,01 en NoData -32768, met DEFLATE en 512 Ã— 512 blokken.
Samen zijn deze bestanden 567,83 MB op disk; alleen relevante blokken
hoeven te worden gelezen. Overviews zijn factor 10 en 50 (5 m en 25 m),
dus er is geen 2 m overzicht. De VRT zelf meldt geen overviews.

Het window eindigt op bronrij 159000, terwijl de VRT maar 150000 rijen
heeft. De zuidelijke **4,5 km ligt buiten de VRT**: minimaal 15,75 miljoen
ontbrekende doelcellen (32,14%). `_validate_source_coverage()` vereist alleen
een intersectie, geen volledige dekking. Vervolgens wordt die buitenstrook
als te vullen NoData behandeld. Deze benchmark representeert dus de huidige
workflow met onvolledige lokale dekking; de hydrologische output is geen
validatie van een volledig door AHN gedekte tegel.
De bronmap bevat 121 TIFFs en de VRT verwijst naar alle 121: er zijn in
deze map geen extra lokale AHN-TIFFs die alleen nog aan de VRT ontbreken.
De aparte, identieke warp zonder NoData-vulling telde **21.660.923
ontbrekende doelcellen (44,206%)**. Naast de buitenstrook zijn er dus ook
andere ontbrekende cellen binnen het gevraagde window.

## Windowed resampling

Het volledige 0,5 m window wordt **niet eerst als NumPy-array gelezen**.
De productiecode geeft een bandhandle door; GDAL splitst de verwerking op
in stukken volgens het warp-geheugenbudget. De GDAL-blokcache komt daar
nog bovenop. Een RSS hoger dan 392 MB is daarom geen bewijs voor een
volledig gematerialiseerd bronarray.
Zie de [Rasterio reproject-API](https://rasterio.readthedocs.io/en/stable/api/rasterio.warp.html)
en [GDAL Warp-geheugenindeling](https://gdal.org/en/stable/programs/gdalwarp.html).

`source.read(1, window=..., out_shape=(7000, 7000),
out_dtype='float64', resampling=Resampling.bilinear)` kan ook rechtstreeks
een 2 m array opleveren, zonder eerst een volledig NumPy-bronarray te maken.
Voor deze specifieke tegel zijn bovendien `boundless=True` en expliciete
NoData nodig: anders kan een gedeeltelijk buitenliggende window op de
dataset worden afgeknipt en naar de verkeerde doeluitgestrektheid worden
geschaald. Bron en doel hebben hier hetzelfde CRS, dus `reproject` doet
resampling, geen verandering van kaartprojectie.
Zie [Rasterio-resampling](https://rasterio.readthedocs.io/en/stable/topics/resampling.html).

De aparte `--mode direct`-proef controleert tevens NoData-maskers en
numerieke verschillen met de oorspronkelijke GDAL-warp. De proef vult
geen NoData en wijzigt de productiecode niet. Beide paden kunnen door
afronding, kernelranden en NoData-behandeling verschillen; een andere
aanroep is niet automatisch een numeriek identieke vervanging.

De proef is daadwerkelijk uitgevoerd, na de volledige baseline:

| Pad | Tijd | Doelarray | Lees-I/O | NoData-cellen |
| --- | ---: | --- | ---: | ---: |
| `read(window, out_shape, boundless=True, bilinear)` | 5,627 s | N f64, 392 MB | 323,30 MB | 19.996.905 |
| Oorspronkelijke `reproject(band, destination)` opnieuw | 8,112 s | N f64, 392 MB | 323,90 MB | 21.660.923 |

De directe read piekte op circa 1,58 GB proces-RSS. De daaropvolgende warp
hield voor vergelijking ook de directe array vast; zijn geheugenpiek is
daarom niet rechtstreeks met de eerste read te vergelijken.
Bij **1.664.018 cellen verschilt de geldigheid** tussen de twee paden.
Op gemeenschappelijk geldige cellen verschillen 5.828.804 waarden met meer
dan 1e-6 opgeslagen eenheid; het maximale verschil is 142,645 cm
(1,426 m), het gemiddelde absolute verschil 0,0714 cm.
Deze proef toont uitvoerbaarheid, maar **geen veilige drop-in-vervanging**.
De precieze verdeling van verschillen over NoData-randen en mosaicnaden is
niet verder geÃ¯soleerd. De circa 2,48 s verschil is bovendien maar 0,13%
van de totale baseline. Dit is geen gerandomiseerde herhaalde snelheidstest;
de bestandscaches zijn niet geleegd.

Ruwe proefgegevens:
`data/profiling_afwateringseenheden/20260910_190650_direct/`.

## Gecontroleerde extra kosten

- Geen volledige landelijke DEM-read en geen NumPy-mosaic: de VRT leest
  de bronblokken via GDAL tijdens de warp. Het doelwindow bepaalt de omvang.
- Bron en doel zijn EPSG:28992. Een aparte projectieomzetting is niet nodig;
  de warp verzorgt wel gridmapping, resampling en NoData-behandeling.
- Het DEM wordt geschreven, volledig teruggelezen voor validatie en opnieuw
  gelezen voor PCRaster. Het segmentraster wordt gelezen door zowel
  `_has_segment_cells()` als `_calculate_pcraster_maps()`.
- De rastervalidatie van LDD/catchments opent alleen metadata; deze leest
  niet nogmaals alle pixels. Polygonisatie gebruikt de bestaande NumPy-array.
- De watersysteemgeometrieÃ«n worden bij rastervoorbereiding met bbox gelezen.
  `_segment_ids_by_fid()` leest daarentegen de volledige segmentlaag inclusief
  geometrieÃ«n opnieuw per tegel. Deze mapping kan in principe vooraf worden
  ingelezen met alleen de benodigde attributen en over tegels worden gedeeld.
- De outputprofielen zetten DEFLATE, maar geen `tiled=True`, blokafmetingen
  of overviews. Bron-TIFFs zijn wel getegeld. Output is dus geen COG; het
  ontbreken van een compressieveld in de VRT betekent niet dat de onderliggende
  AHN-bestanden ongecomprimeerd zijn.
- Grote tijdelijke arrays ontstaan op het 2 m grid: twee maskers, geneste
  `np.where`, subtractie, `np.rint`, validiteitsmaskers en casts. Een enkele
  float64-kopie kost 392 MB. `astype(int32)` kopieert ook een reeds int32
  segmentarray; na `pcr2numpy` volgen eveneens aanvullende casts.
- Er worden geen PCRaster `.map`-bestanden geschreven: de conversies zijn
  in-memory. Tijdelijke GeoTIFFs worden atomair hernoemd, niet nogmaals
  gekopieerd. Het teruglezen van de vectoroutput dient feature-countvalidatie.
- Downloaden, VRT-opbouw en watersysteemvoorbereiding staan al buiten de
  tegellus. DEM-voorbewerking van overlappende buffers gebeurt wel opnieuw:
  een 14 Ã— 14 km rekengebied tegenover een 10 Ã— 10 km kern betekent in een
  groot regelmatig tegelraster ongeveer factor 1,96 verwerkt oppervlak.

## Drie grootste bottlenecks en prioriteiten

1. **`lddcreate`: 1066,976 s (54,11%).** Deze native berekening verwerkt
   49 miljoen cellen en omvat stromingsrichtingen en pitverwijdering,
   niet alleen conversie van rasterformaten. Er is geen data-I/O gemeten.
   Grote geÃ¯nterpoleerde vlakken kunnen de berekening beÃ¯nvloeden, maar hun
   afzonderlijke bijdrage is niet met een tweede DEM gemeten. Zie de
   [PCRaster-beschrijving van lddcreate](https://pcraster.geo.uu.nl/pcraster/4.4.2/documentation/pcraster_manual/sphinx/op_lddcreate.html).
2. **NoData vullen: 889,455 s (45,10%).** 44,2% van het doelgrid ontbreekt,
   terwijl de zoekafstand 9899,49 cellen is, circa 19,8 km. De GDAL-methode
   zoekt per ontbrekende cel in vier richtingssectoren; een grote lege
   buitenstrook is veel duurder dan kleine gaten. Ook hier is geen
   data-I/O gemeten. Zie [GDALFillNodata](https://gdal.org/en/stable/api/gdal_alg.html).
3. **DEM-window/mosaic/resampling: 8,110 s (0,41%).** Honderden miljoenen
   mogelijke broncellen, decompressie van relevante 512 Ã— 512 blokken en
   bilineaire filtering kosten tijd, maar zijn hier van secundair belang.

Concrete optimalisaties, in volgorde van verwachte winst:

1. **Voorkom herberekening bij ongewijzigde inputs en instellingen.** De
   huidige Aa-en-Maas-scriptinstelling `overwrite=True` forceert elke keer
   de volledige keten. Bestaand hergebruik kan bij identieke inputs vrijwel
   alle gemeten tijd vermijden. Controleer daarbij zelf dat bronversie en
   rekenparameters overeenkomen; de huidige hergebruikcontrole vergelijkt
   niet al die parameters. Er is in dit onderzoek niets omgezet.
2. **Herstel de dekking en valideer die vÃ³Ã³r de berekening.** Vul de ontbrekende
   brondata aan voor het gehele gebufferde window en onderscheid interne
   kleine gaten van ontbrekende dekking. Behandel kilometers ontbrekende
   buitenruimte niet automatisch als een te interpoleren gat. Pas daarna
   een onderbouwde begrensde/gelaagde NoData-vulling of caching van het
   ongewijzigde voorbereide DEM beoordelen. Potentieel raakt dit de huidige
   889 s filltijd; de werkelijke winst met complete data is nog niet gemeten.
3. **Pak daarna het herhalen van `lddcreate` aan.** Hergebruik LDD bij een
   identiek gebrand DEM, grid en PCRaster-instellingen. Voor een batch kan
   procesparallelisme per tegel de totale doorlooptijd verminderen, met
   een expliciet geheugenbudget; dat versnelt niet deze ene aanroep.
   Kleiner grid, andere pitdrempels of een andere engine veranderen het
   hydrologische probleem en vergen afzonderlijke validatie.
4. **Optimaliseer daarna de DEM-aanvoer voor herhaalde workflows.** Een
   uitgelijnd 2 m basis-DEM/COG kan terugkerende 0,5 m decompressie en
   resampling voorkomen. Vergelijk hoogtewaarden, NoData en gridranden
   voordat zo'n product de huidige warp vervangt. De gemeten directe
   `read(out_shape=...)` is daarvoor nog niet numeriek gelijkwaardig.
5. **Raster-I/O en arraykopieÃ«n pas daarna.** Doorgeven van bestaande arrays,
   attribuut-only segmentmapping eenmaal vooraf, minder validatiereads en
   passend getegelde TIFFs besparen geheugen en kleine hoeveelheden tijd.
   De vier rasterwrites samen kosten slechts 0,54 s; dit is geen prioriteit
   voor het versnellen van deze tegel. Validatie en atomair vervangen behouden.

## Advies: eenmalig 2 m DEM/COG of on-the-fly?

**Voor een enkele run: behoud voorlopig het huidige windowed GDAL-warp-pad.**
Het materialiseert het 0,5 m NumPy-window niet en kost slechts 8,11 s.
Een extra preprocessiestap betaalt zich voor deze ene run niet terug;
NoData-vulling en PCRaster nemen samen 99,21% van de tijd in beslag.
Alleen een sneller bronformaat kan daarom zelfs in het ideale geval
minder dan circa 0,42% van deze totale baseline wegnemen.

**Voor veel overlappende tegels en herhaalde runs: eenmalig een correct
uitgelijnd 2 m DEM/COG is zinvol om te onderzoeken, na herstel van de dekking.**
Er zijn 16 keer minder cellen dan op 0,5 m en gebufferde tegels verwerken
veel dezelfde bronruimte. Gebruik de rekenbalans
`preprocessingtijd + K Ã— leestijd_2m < K Ã— leestijd_en_resampling_0.5m`.
De 2 m COG-leestijd en volledige preprocessingtijd zijn hier niet gemeten,
dus er is nog geen onderbouwd numeriek omslagpunt.

Een **alleen geresampled** 2 m product verwijdert de 889 s NoData-vulling
en de 1067 s LDD-berekening niet. Hergebruik van een correct gevuld,
ongebrand basis-DEM kan de filltijd wel vermijden; bronversie, grid,
NoData-methode, schaal/offset en afronding moeten daarbij expliciet zijn.
Een regionale vulling kan bij tegelranden andere hoogten opleveren dan
vulling per tegel. Ook vooraf afronden naar int16 kan andere resultaten
geven dan de huidige volgorde resamplen â†’ vullen â†’ branden â†’ afronden.
Daarom eerst hoogte-, masker- en afwateringsresultaten vergelijken en pas
daarna het gekozen preprocessiepad als productie-optimalisatie invoeren.


## Hervalidatie met volledige TIFF-extents

De coverage-definitie is gewijzigd naar `union(full_extent_of_each_source_tif)`.
Alleen TIFF-bounds en georeferentie bepalen de dekking; bronmaskers en pixelwaarden
worden daarvoor niet gelezen. De interpolatiemethode en zoekafstand zijn behouden.
De bovenstaande oorspronkelijke benchmark blijft als historische meting staan.

Opnieuw gemeten met `scripts/profile_dem_coverage.py` in de pixi-omgeving
`afwateringseenheden`, voor bounds `(168000, 358000, 182000, 372000)`,
EPSG:28992, 2 m en 7000 × 7000 cellen. Deze hervalidatie draait de
rastervoorbereiding; PCRaster/lddcreate is niet opnieuw uitgevoerd.

| Grootheid | Resultaat |
| --- | ---: |
| Onderliggende TIFFs in VRT | 121 |
| TIFFs met overlap met benchmarktegel | 7 |
| Coverage | 30.125.000 cellen (120,5 km²; 61,48%) |
| NoData binnen coverage vóór interpolatie | 2.785.923 cellen |
| NoData buiten coverage vóór en na interpolatie | 18.875.000 cellen |
| Geïnterpoleerd | 2.785.923 cellen |
| NoData binnen coverage na interpolatie | 0 cellen |
| Coverage opbouwen met lege extent-cache | 0,207 s |
| Coverage met gevulde extent-cache | 0,036 s |
| Interpolatie eerste / tweede run | 0,933 / 0,959 s |

Alle oorspronkelijke geldige hoogtewaarden zijn exact behouden; buiten coverage
is niets geïnterpoleerd. Ook de opgeslagen DEM-maskers zijn gecontroleerd.
De tweede run had 121 cachehits. De Windows-bestandscache is niet geleegd;
leeg/gevuld verwijst hier uitsluitend naar de in-memory coverage-cache.

Ruwe resultaten en diagnostische rasters:
`data/profiling_afwateringseenheden/20260910_195641_coverage/`
(`cold.json`, `warm.json` en de submappen `cold` en `warm`).
