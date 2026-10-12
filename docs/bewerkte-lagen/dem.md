---
editorial_status: ai
---

# DEM (WSWO)

## Doel

Deze bewerking combineert het AHN-terreinmodel met één afgeleide hoogte per
individueel gebouw. De gebouwcellen volgen exact het bronnenraster van
[functioneel landgebruik](functioneel-landgebruik.md).

## Bronlagen

- [AHN-DTM](../bronlagen/ahn.md), inclusief omliggende rastertegels.
- De landgebruiktegels met `bronnen`, `gebouw_ids` en volledige voorbereide
  gebouwgeometrieën. De oorspronkelijke [BAG-identificatie](../bronlagen/bag.md)
  blijft in deze afgeleide gebouwgegevens bewaard. De DEM-bewerking selecteert
  zelf geen BAG-panden.

## Werkwijze

### Gebouwcellen selecteren

Gebouwcellen zijn uitsluitend cellen met broncode `10`. Tijdens de
landgebruikproductie krijgen de reeds voorbereide panden een compact, positief
gebouw-ID. Dezelfde geometrieën, rijvolgorde en rasterregels bepalen het
ID-raster. Hogere bronprioriteiten, zoals water, verwijderen daar het gebouw-ID.
Ook gebouwen met een nog onbekende landgebruiksklasse behouden hun ID.
Daarmee geldt `(gebouw_ids > 0) == (functioneel_landgebruik_bronnen == 10)`.
Aangrenzende panden blijven afzonderlijke gebouwen.

### Gebouwhoogten bepalen

Voor ieder geselecteerd gebouw wordt de volledige voorbereide geometrie
gebruikt, ook als deze een tegelgrens overschrijdt. De bewerking zoekt originele
AHN-cellen met hun celmidden in de buitenring rond het gebouw. Cellen van
voorbereide gebouwen, inclusief buurpanden, zijn uitgesloten als donor.
De eerste zoekafstand is standaard 1 m. Als er geen geldige donor is, groeit
de afstand telkens met 1 m, tot maximaal 5 m. Bij de eerste geslaagde zoekactie
wordt het 75e percentiel berekend. Er wordt geen vaste vloerhoogtetoeslag toegepast.

De hoogte, BAG-identificatie, zoekafstand en het aantal donors worden bewaard
in `gebouwhoogten.gpkg`. Iedere tegel gebruikt dezelfde opgeslagen hoogte voor
hetzelfde gebouw. Ontbreekt een donor binnen de maximale gebouwzoekafstand,
dan blijft de oorspronkelijke of aangevulde terreinwaarde onder dat gebouw
beschikbaar. Het gebouw blijft als mislukte hoogteschatting in `nodata.gpkg`
staan; alleen een geslaagde gebouwhoogte krijgt voorrang op het terrein.

### AHN interpoleren

AHN-gaten worden onafhankelijk van de gebouwhoogten ingevuld met lokale
inverse-afstandsinterpolatie, zonder extra gladstrijken. De maximale afstand
is instelbaar in meters (standaard 250 m) en wordt naar rasterpixels omgerekend.
Dit is een harde grens: de zoekafstand groeit niet automatisch en nieuwe
interpolatiewaarden worden nooit als donor gebruikt. Alleen ontbrekende
AHN-cellen worden geïnterpoleerd. Originele geldige waarden blijven exact
behouden, behalve waar de uiteindelijke gebouwlaag voorrang krijgt.
Er is voor deze DEM-interpolatie **geen beperking tot `landgebied`**.
De bestaande landgebruikaanvulling houdt haar eigen landmasker, toegestane
donorbronnen en categorische dichtstbijzijnde-buurmethode. Beide gebruiken
dezelfde maskergestuurde interpolatiefunctie.

Voor eigen workflows is er ook een losse AHN-tegelbewerking. Die leest een VRT
of verzameling AHN-tegels en schrijft ingevulde GeoTIFFs, optioneel met een
nieuwe VRT. De rastereigenschappen volgen de brontegels. Een doelmasker kan
bepalen welke gaten mogen worden gevuld, onafhankelijk van de donors.
De maximale zoekafstand begrenst de interpolatie; NoData buiten de
bronextents wordt niet door de brondekking opgelost.

### Tegels samenstellen

De berekening gebruikt het tegelrooster en de pixeluitlijning van functioneel
landgebruik. De overlap is de maximale interpolatieafstand, naar boven afgerond
op hele pixels, plus een extra pixel voor uitlijning. Hierdoor zijn donors
buiten de tegel beschikbaar; de extra pixel vergroot de toegestane donorafstand niet.
Alleen de tegelkern wordt geschreven. AHN en landgebruik moeten dezelfde CRS,
resolutie en pixeluitlijning hebben; de bewerking herschaalt ze niet stilzwijgend.

### BAG-vloerpeilen in eigen workflows

Naast de standaard DEM-productie is er een losse bewerking voor
[BAG-panden](../bronlagen/bag.md) en een aangeleverd DEM, bijvoorbeeld AHN.
Daarbij wordt per pand een vloerpeil uit het DEM afgeleid. Een bufferstap
bepaalt welke omgeving bij de hoogteschatting wordt betrokken. De pandgeometrie
wordt vervolgens met die waarde gerasteriseerd op het grid van het DEM.

Deze losse bewerking schrijft één GeoTIFF met het afgeleide vloerpeil binnen
de panden en legt de waarde als `vloerpeil` vast in de gebruikte
BAG-GeoDataFrame. Het resultaat hangt af van de kwaliteit, dekking en resolutie
van het DEM en van de geselecteerde panden; het is geen zelfstandig BAG-brongegeven.
De standaard DEM-productie gebruikt de hierboven beschreven gebouwhoogten uit
de voorbereide landgebruikgeometrieën.

## Uitvoer

- `dem.vrt` en COG `dem.tif`: AHN met geïnterpoleerde gaten en gebouwhoogten.
- COG `dem_float.tif`: directe Float32-hoogten in meters, met schaalfactor 1
  en offset 0.
- `dem_bron.vrt` en COG `dem_bron.tif`: de herkomst van de uiteindelijke hoogte.
- `ahn_bron.vrt` en COG `ahn_bron.tif`: terreinherkomst voor de gebouwlaag;
  1 = origineel AHN, 3 = interpolatie, 0 = ontbrekend terrein.
- `nodata.gpkg`, laag `nodata`: onopgeloste gebouwen en resterende AHN-gaten.
- `gebouwhoogten.gpkg`: herbruikbare hoogten per individueel gebouw.
- `tiles.gpkg`: de geselecteerde tegelkernen van het productiegebied.
- Per tegel `tiles/<tile_id>/`: `ahn_aangevuld.tif`, `ahn_bron.tif`,
  `gebouwhoogten.tif`, `dem_bron.tif`, `nodata.gpkg`, `status.json` en `workflow.log`.
  De tegelnaam bevat `xmin_ymin_xmax_ymax`.

| `dem_bron` | Betekenis |
| --- | --- |
| 0 | NoData / onopgelost |
| 1 | Origineel AHN-DTM |
| 2 | Gebouwhoogte |
| 3 | Geïnterpoleerd AHN |

Het VRT leest eerst `ahn_aangevuld.tif` en daarna de gebouwlaag. Gebouwhoogten krijgen
voorrang. De hoogteopslag behoudt het AHN-datatype, schaalfactor en offset;
nieuwe waarden worden zo nodig afgerond naar de oorspronkelijke opslageenheid.
Hoogteoverzichten gebruiken gemiddelden; broncodes en ID's dichtstbijzijnde buren.

`dem_float.tif` wordt afgeleid van het voltooide `dem.tif`:
`hoogte = opgeslagen waarde * schaalfactor + offset`. Het bestand bevat dezelfde
reeds afgeronde hoogten; het levert geen extra meetnauwkeurigheid. De omzetting
naar Float32 kan kleine afrondingsverschillen geven. Het rasterrooster en de
geldigheidsmaskers blijven gelijk. Ontbrekende cellen krijgen NaN, ook waar
NoData buiten `landgebied` of in open water is toegestaan.
`ahn_bron` en `dem_bron` gelden voor beide DEM-bestanden.

De float-COG gebruikt verliesvrije ZSTD-compressie op niveau 9, met een
floating-point predictor voor raster en overzichten. Overzichten worden opnieuw
uit de float-hoogten berekend met gemiddelden. De opslag en compressie van
`dem.tif` veranderen niet.

`nodata.gpkg` bevat `bron`, `categorie`, `reden`, `identificatie`, `gebouw_id`,
`zoekafstand_m`, `donor_aantal` en geometrie. Onopgeloste gebouwen staan er
eenmalig met hun volledige geometrie in; resterende AHN-gaten volgen de
ontbrekende rastercellen per tegel. De categorieen zijn:

| `categorie` | Betekenis |
| --- | --- |
| `Gebouw` | Geen gebouwhoogte bepaald; de oorspronkelijke gebouwmelding blijft behouden |
| `AHN_water` | AHN-gat na interpolatie bij landgebruikcode 100 of 228 |
| `AHN_overig` | AHN-gat na interpolatie bij ander landgebruik, inclusief onbekend/code 0 |

AHN-gaten worden bepaald voordat gebouwhoogten worden toegevoegd. Een AHN-gat
dat door een geldige gebouwhoogte wordt bedekt blijft daarom in de diagnostiek
zichtbaar, terwijl het eind-DEM daar wel een waarde heeft. De polygonen volgen
de exacte rastercelgrenzen en worden ook buiten `landgebied` opgenomen.

Resterende NoData blokkeert de publicatie van het DEM niet. De maximale
interpolatieafstand blijft gelden; ontbrekende waarden worden niet kunstmatig
gevuld. `dem_coverage.json` telt de ontbrekende cellen in het uiteindelijke DEM,
na de gebouwlaag: `outside_landgebied`, `open_water` (binnen `landgebied`) en
`inside_landgebied_nonwater`. De landsgrens wordt bepaald op basis van celmiddens.
Publicatie betekent dus niet dat het DEM volledige hoogtedekking heeft.

## Aandachtspunten en beperkingen

Gebouwhoogten zijn afgeleide schattingen, geen ingemeten vloerpeilen.
De maximale zoekafstanden begrenzen welke gaten kunnen worden opgelost.
Bekijk daarom altijd `nodata.gpkg`, `ahn_bron` en `dem_bron`. De gebouwdiagnostiek kan een
volledige geometrie tonen waarvan slechts een deel in het uitvoergebied ligt.
Bewaar de tegelbestanden zolang het VRT nodig is.

## Zelf produceren

Begin met [DEM-productie voor Nederland of Alkmaar](../produceren/dem.md).
De Python-interface staat bij [DEM-API](../reference/dem.md).

Voor de losse AHN-tegelbewerking gebruikt een eigen Python-workflow
`get_ahn_rasters` en `interpolate_ahn_tiles`; zie de [AHN-API](../reference/ahn.md).
De losse BAG-vloerpeilbewerking gebruikt `rasterize_bag`; zie de
[BAG-API](../reference/bag.md).
