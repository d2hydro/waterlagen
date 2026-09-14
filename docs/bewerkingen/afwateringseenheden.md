# Afwateringseenheden

## Doel

Deze bewerking leidt tot `afvoergebieden` gekoppeld aan `hydroobjecten`.

## Bronnen

- [GKW HYDAMO](../bronnen/hydamo.md)
- [AHN](../bronnen/ahn.md)

## Werkwijze

### Voorbewerken watersysteem
Vanuit de geleverde (Hy)DAMO set worden:

- `primaire` en `secundaire` `hydroobjecten` en relevante `verbindingspunten` (bijvoorbeeld `gemalen` en `stuwen`) uitgelezen. De gebruiker kan hierbij een gebied en/of waterbeheerder specificeren.
- `Primaire` hydroobjecten worden bij de relevante `verbindingspunten` en op een maximale lengte (standaard 500 meter) opgesplitst naar `hydroobject-segmenten`.
- `Verbindingspunten` vormen een gericht netwerk, waarbijj `van_segment` en `naar_segment` de richting vormen. Van opgegeven punten (`stuwen`, `gemalen`, etc.) worden tevens de oorspronkelijke eigenschappen bewaard, zodat deze herkenbaar blijven.
- `Secundaire hydroobjecten` worden opgesplitst in een set die wél en een set die níet verbonden is met de `primaire hydroobjecten`.

### Afleiden afwateringseenheden
Op basis van het [AHN-DTM](../bronnen/ahn.md) en hierboven genoemde watersysteem worden:

- Het DTM (0.5 x 0.5 meter) geschaald ingelezen op 2x2 meter (instelbaar) en dichtgeinterpoleerd.
- Hier worden hydroobjecten ingebrand. Primaire  hydroobjecten krijgen tweemaal en secundaire segmenten eenmaal de ingestelde branddiepte; bij overlap heeft primair voorrang.
- De `hydroobject-segmenten` worden ingebrand op een grid gelijk aan het voorbewerkte DTM, een cel onder een `hydroobject-segment` krijgt de unieke feature index (`fid`) van het betreffende segment
- Vervolgens worden het [Local Drainage Direction (LDD)](https://pcraster.geo.uu.nl/pcraster/4.4.2/documentation/pcraster_manual/sphinx/op_lddcreate.html) berekend op basis van het voorbewerkte DTM met gebrande waterlopen. Een LDD bepaald per cel de lokale afstroomrichting. De routine zal hierbij lokale depressies opvullen tot een maximale diepte. De maximale diepte is ingesteld op 50% van de ingestelde branddiepte. De branddiepte is zodanig diep ingsteld (bijvoorbeeld 500 meter), zodat de LDD de volgende logica volgt:

    - een gebied met maaiveld cellen vindt altijd een richting naar een `secundaire` of `primaire` waterloopcel.
    - cellen met `secundaire` waterlopen vinden altijd een richting naar een `primaire` waterloopcel.

- Vanuit het LDD en de verrasterde `hydroobject-segmenten` word een raster met [`subcatchments`](https://pcraster.geo.uu.nl/pcraster/4.4.2/documentation/pcraster_manual/sphinx/op_subcatchment.html) berekend. Hiermee krijgen alle cellen van het raster de `fid` van het corresponderende `hydroobject-segment`.
- De berekende `subcachments` worden als laatste stap omgezet naar `afwateringseenheden`. Elke afwateringseenheid is een polygoon dat het afstroomgebied voorsteld van een `hydroobject-segment`. Naast de `fid` is de oorspronkelijke `segment` en `hydroobject` informatie toegevoegd.

Grote gebieden kunnen in gebufferde tegels worden berekend:

- Het gebied wordt opgedeeld in vierkante kerntiles. De standaard tegelgrootte is 5 × 5 km.
- Per kerntile wordt de berekening uitgevoerd op de tile inclusief een buffer. De standaard buffer is 2 km, zodat afstroming van buiten de kerntile kan worden meegenomen.
- Alleen afwateringseenheden die niet tot aan de binnenrand van de buffer reiken, worden teruggeknipt naar de kerntile en meegenomen in het resultaat.
- De bruikbare resultaten worden per `segment_id` samengevoegd en teruggeknipt naar het oorspronkelijke gebied.
- Tegels zonder `hydroobject-segmenten` worden overgeslagen. Wanneer een afwateringseenheid de buffergrens bereikt, wordt de tegel gemeld als randprobleem en kan deze met een grotere buffer opnieuw worden berekend.

Na het berekenen van afwateringseenheden per tegel worden alle tegels samengevoegd tot 1 set afwateringseenheden voor het interessegebied.

## Uitvoer

`watersysteem.gpkg` bevat de volgende lagen:

- `hydroobject_primair`: primaire watergangen uit HyDAMO.
- `hydroobject_secundair`: secundaire watergangen die ruimtelijk verbonden zijn met het primaire systeem.
- `hydroobject_secundair_niet_verbonden`: secundaire watergangen zonder ruimtelijke verbinding met het primaire systeem.
- `hydroobject_segment`: primaire watergangen, opgeknipt bij kunstwerken/aansluitingen en in beheersbare segmenten.
- `hydroobject_verbinding`: gerichte (van_segment, naar_segement, op basis van tekenrichting hydrooobjecten) topologische verbindingen tussen de watergangsegmenten.

`afwateringseenheden.gpkg` bevat polygonen van de berekende afwateringsgebieden, elk gekoppeld aan het hydroobject_segment waarnaar het oppervlak afwatert.

De standaardproject-CRS is `EPSG:28992`. Elke laag heeft tevens een voorgedefinieerde stijldefinitie die automatisch wordt herkend door QGIS.

## Aandachtspunten en beperkingen

Secundaire objecten gelden als verbonden wanneer hun volledige geometrie binnen
de ingestelde tolerantie (standaard 2 m) van een primair of secundair object
ligt. Tegels zonder segmentcellen worden overgeslagen. Als een gebied vanaf de
buffergrens de kerntile bereikt, meldt Waterlagen de tile als randprobleem;
vergroot dan de buffer en bereken die tile opnieuw.

## Zelf produceren

Voor het zelf produceren zie het werkende voorbeeld voor waterschap Aa en Maas onder [zelf produceren](../produceren/afwateringseenheden.md) als voorbeeld

Voor het gebruiken van onderliggende Python-functies zie de [API-referentie](../reference/afwateringseenheden.md).
