# DEM met gebouwen

## Doel

Deze bewerking combineert het AHN-terreinmodel met één afgeleide hoogte per
individueel gebouw. De gebouwcellen volgen exact het bronnenraster van
[functioneel landgebruik](functioneel-landgebruik.md).

## Bronnen

- [AHN-DTM](../bronnen/ahn.md), inclusief omliggende rastertegels.
- De landgebruiktegels met `bronnen`, `gebouw_ids` en volledige voorbereide
  gebouwgeometrieën. De oorspronkelijke [BAG-identificatie](../bronnen/bag.md)
  blijft in deze afgeleide gebouwgegevens bewaard. De DEM-bewerking selecteert
  zelf geen BAG-panden.

## Werkwijze

Gebouwcellen zijn uitsluitend cellen met broncode `10`. Tijdens de
landgebruikproductie krijgen de reeds voorbereide panden een compact, positief
gebouw-ID. Dezelfde geometrieën, rijvolgorde en rasterregels bepalen het
ID-raster. Hogere bronprioriteiten, zoals water, verwijderen daar het gebouw-ID.
Ook gebouwen met een nog onbekende landgebruiksklasse behouden hun ID.
Daarmee geldt `(gebouw_ids > 0) == (functioneel_landgebruik_bronnen == 10)`.
Aangrenzende panden blijven afzonderlijke gebouwen.

Voor ieder geselecteerd gebouw wordt de volledige voorbereide geometrie
gebruikt, ook als deze een tegelgrens overschrijdt. De bewerking zoekt originele
AHN-cellen met hun celmidden in de buitenring rond het gebouw. Cellen van
voorbereide gebouwen, inclusief buurpanden, zijn uitgesloten als donor.
De eerste zoekafstand is standaard 1 m. Als er geen geldige donor is, groeit
de afstand telkens met 1 m, tot maximaal 5 m. Bij de eerste geslaagde zoekactie
wordt het 75e percentiel berekend. Er wordt geen vaste vloerhoogtetoeslag toegepast.

De hoogte, BAG-identificatie, zoekafstand en het aantal donors worden bewaard
in `gebouwhoogten.gpkg`. Iedere tegel gebruikt dezelfde opgeslagen hoogte voor
hetzelfde gebouw. Ontbreekt een donor binnen 5 m, dan blijven alle DEM-cellen
van het gebouw NoData. Ook eventueel onderliggend AHN wordt daar afgeschermd,
zodat het VRT geen alternatieve hoogte teruggeeft.

AHN-gaten worden onafhankelijk van de gebouwhoogten ingevuld met lokale
inverse-afstandsinterpolatie, zonder extra gladstrijken. De maximale afstand
is instelbaar in meters en wordt naar rasterpixels omgerekend. Alleen ontbrekende
AHN-cellen worden geïnterpoleerd. Originele geldige waarden blijven exact
behouden, behalve waar de uiteindelijke gebouwlaag voorrang krijgt.
Er is voor deze DEM-interpolatie **geen beperking tot `landgebied`**.
De bestaande landgebruikaanvulling houdt haar eigen landmasker, toegestane
donorbronnen en categorische dichtstbijzijnde-buurmethode. Beide gebruiken
dezelfde maskergestuurde interpolatiefunctie.

De berekening gebruikt het tegelrooster en de pixeluitlijning van functioneel
landgebruik. Overlap rond elke tegel maakt AHN-donors buiten de tegel beschikbaar.
Alleen de tegelkern wordt geschreven. AHN en landgebruik moeten dezelfde CRS,
resolutie en pixeluitlijning hebben; de bewerking herschaalt ze niet stilzwijgend.

## Uitvoer

- `dem.vrt` en COG `dem.tif`: AHN met geïnterpoleerde gaten en gebouwhoogten.
- `dem_bron.vrt` en COG `dem_bron.tif`: de herkomst per cel.
- `nodata.gpkg`, laag `nodata`: onopgeloste gebouwen en resterende AHN-gaten.
- `gebouwhoogten.gpkg`: herbruikbare hoogten per individueel gebouw.
- `tiles.gpkg`: de vier geselecteerde tegelkernen bij de Alkmaar-scriptproductie.
- Tegelkernen onder `tiles/ahn_filled`, `tiles/gebouwen` en `tiles/dem_bron`.

| `dem_bron` | Betekenis |
| --- | --- |
| 0 | NoData / onopgelost |
| 1 | Origineel AHN-DTM |
| 2 | Gebouwhoogte |
| 3 | Geïnterpoleerd AHN |

Het VRT leest eerst `ahn_filled` en daarna de gebouwlaag. Gebouwhoogten krijgen
voorrang. De hoogteopslag behoudt het AHN-datatype, schaalfactor en offset;
nieuwe waarden worden zo nodig afgerond naar de oorspronkelijke opslageenheid.
Hoogteoverzichten gebruiken gemiddelden; broncodes en ID's dichtstbijzijnde buren.

`nodata.gpkg` bevat `bron`, `reden`, `identificatie`, `gebouw_id`,
`zoekafstand_m`, `donor_aantal` en geometrie. Onopgeloste gebouwen staan er
eenmalig met hun volledige geometrie in; resterende AHN-gaten volgen de
ontbrekende rastercellen per tegel. De productie stopt niet vanwege deze gaten.

## Aandachtspunten en beperkingen

Gebouwhoogten zijn afgeleide schattingen, geen ingemeten vloerpeilen.
De maximale zoekafstanden begrenzen welke gaten kunnen worden opgelost.
Bekijk daarom altijd `nodata.gpkg` en `dem_bron`. De gebouwdiagnostiek kan een
volledige geometrie tonen waarvan slechts een deel in het uitvoergebied ligt.
Bewaar de tegelbestanden zolang het VRT nodig is.

## Zelf produceren

Begin met [de viertegelsproef rond Alkmaar](../produceren/dem.md).
De Python-interface staat bij [DEM-API](../reference/dem.md).
