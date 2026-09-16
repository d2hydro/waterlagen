# Afwateringseenheden

## Doel

Deze bewerking leidt tot `afvoergebieden` gekoppeld aan `hydroobjecten`.

## Bronnen

- [GKW HYDAMO](../bronnen/hydamo.md)
- [AHN](../bronnen/ahn.md)
- [Bestuurlijke gebieden](../bronnen/bestuurlijke-gebieden.md) voor begrenzing tot Nederland

## Werkwijze

### Voorbewerken watersysteem

Vanuit de geleverde (Hy)DAMO-set worden:

- `primaire` en `secundaire` `hydroobjecten` en relevante `verbindingspunten` (bijvoorbeeld `gemalen` en `stuwen`) uitgelezen. De gebruiker kan hierbij een gebied en/of waterbeheerder specificeren.
- `Primaire` hydroobjecten worden bij de relevante `verbindingspunten` en op een maximale lengte (standaard 500 meter) opgesplitst naar `hydroobject-segmenten`.
- `Verbindingspunten` vormen een gericht netwerk, waarbij `van_segment` en `naar_segment` de richting vormen. Van opgegeven punten (`stuwen`, `gemalen`, etc.) worden tevens de oorspronkelijke eigenschappen bewaard, zodat deze herkenbaar blijven.
- `Secundaire hydroobjecten` worden opgesplitst in een set die wél en een set die níet verbonden is met de `primaire hydroobjecten`.

### Afleiden afwateringseenheden

Op basis van het [AHN-DTM](../bronnen/ahn.md) en het hierboven genoemde watersysteem worden de volgende stappen uitgevoerd:

- Het DTM (0,5 × 0,5 meter) wordt geschaald ingelezen op 2 × 2 meter (instelbaar) en binnen de brondekking dichtgeïnterpoleerd.
- Hier worden hydroobjecten ingebrand. Primaire hydroobjecten krijgen tweemaal en secundaire segmenten eenmaal de ingestelde branddiepte; bij overlap heeft primair voorrang.
- De `hydroobject-segmenten` worden ingebrand op een grid gelijk aan het voorbewerkte DTM. Een cel onder een `hydroobject-segment` krijgt de unieke feature-index (`fid`) van het betreffende segment.
- Vervolgens wordt de [Local Drainage Direction (LDD)](https://pcraster.geo.uu.nl/pcraster/4.4.2/documentation/pcraster_manual/sphinx/op_lddcreate.html) berekend op basis van het voorbewerkte DTM met gebrande waterlopen. Een LDD bepaalt per cel de lokale afstroomrichting. De routine zal hierbij lokale depressies opvullen tot een maximale diepte. De maximale diepte is ingesteld op 50% van de ingestelde branddiepte. De branddiepte is zo diep ingesteld (bijvoorbeeld 500 meter) dat de LDD de volgende logica volgt:

    - een gebied met maaiveldcellen vindt altijd een richting naar een `secundaire` of `primaire` waterloopcel.
    - cellen met `secundaire` waterlopen vinden altijd een richting naar een `primaire` waterloopcel.

- Vanuit de LDD en de verrasterde `hydroobject-segmenten` wordt een raster met [`subcatchments`](https://pcraster.geo.uu.nl/pcraster/4.4.2/documentation/pcraster_manual/sphinx/op_subcatchment.html) berekend. Hiermee krijgen alle cellen van het raster de `fid` van het corresponderende `hydroobject-segment`.
- De berekende `subcatchments` worden als laatste stap omgezet naar `afwateringseenheden`. Elke afwateringseenheid is een polygoon die het afstroomgebied voorstelt van een `hydroobject-segment`. Naast de `fid` is de oorspronkelijke informatie over het segment en het hydroobject toegevoegd.

Grote gebieden kunnen in gebufferde tegels worden berekend:

- Het gebied wordt opgedeeld in vierkante kerntiles. De standaardtegelgrootte is 5 × 5 km.
- Per kerntile wordt de berekening uitgevoerd op de tile inclusief een buffer. De standaardbuffer is 2 km, zodat afstroming van buiten de kerntile kan worden meegenomen.
- Alleen afwateringseenheden die niet tot aan de buitenste rekenrand van de buffer reiken, worden teruggeknipt naar de kerntile en meegenomen in het resultaat.
- De bruikbare resultaten worden per `segment_id` samengevoegd en teruggeknipt naar het oorspronkelijke gebied.
- Tegels zonder `hydroobject-segmenten` worden overgeslagen. Wanneer een afwateringseenheid vanaf de buffergrens de kerntile bereikt, wordt de tegel gemeld als randprobleem.

Na het berekenen van afwateringseenheden per tegel worden alle tegels samengevoegd tot één set afwateringseenheden voor het interessegebied.

### DEM-dekking en interpolatie

De dekking is de vereniging van de volledige rechthoekige extents van de
onderliggende hoogterasters. Overlap telt eenmaal. Ook NoData aan de rand of
binnen een bronraster valt binnen dekking en wordt geïnterpoleerd. Buiten alle
bronextents blijft NoData behouden.

De dekking kan worden begrensd tot de Nederlandse landsgrens, zoals in het
Aa en Maas-script. De celmiddens bepalen of cellen binnen Nederland vallen,
ook in de tegelbuffers. Buitenliggende cellen worden vóór interpolatie op
NoData gezet; ze worden niet gevuld en leveren geen hoogte voor interpolatie.
Blijven binnen de dekking cellen leeg, dan krijgen alleen die cellen de
dichtstbijzijnde oorspronkelijke geldige hoogte binnen de dekking. Bestaande
hoogtes en al geïnterpoleerde cellen blijven behouden. Zonder bruikbare hoogte
binnen de dekking om aanwezige gaten te vullen, stopt de berekening met een foutmelding.

### Opschonen en aanvullen bij het samenvoegen

Losse lijn- en puntresten worden verwijderd. Gaten worden waar mogelijk gevuld
vanuit bruikbare buurpolygonen, zonder een nieuwe LDD te berekenen. Polygonen
die hun buitenste rekenrand raken vallen af. De buur met de meeste dekking
krijgt voorrang; bij gelijke dekking volgen de grootste randafstand en daarna
het tegel-ID. Alleen lege ruimte wordt aangevuld: bestaande toewijzingen blijven
behouden. Zonder bruikbare buur blijft een gat open, ook bij een grotere buffer.

### Optioneel Duits hoogtemodel

Voor een eigen grensoverschrijdende workflow kan [DGM1](../bronnen/dgm1.md)
AHN aanvullen. De voorbereiding maakt aparte 1m-tegels in RD/NAP en een
gecombineerde VRT waarin geldige AHN-hoogtes voorrang hebben. De originele
DGM1-bestanden blijven behouden. Het Aa en Maas-script gebruikt uitsluitend
AHN en begrenst de interpolatie tot Nederland.

## Uitvoer

`watersysteem.gpkg` bevat de volgende lagen:

- `hydroobject_primair`: primaire watergangen uit HyDAMO.
- `hydroobject_secundair`: secundaire watergangen die ruimtelijk verbonden zijn met het primaire systeem.
- `hydroobject_secundair_niet_verbonden`: secundaire watergangen zonder ruimtelijke verbinding met het primaire systeem.
- `hydroobject_segment`: primaire watergangen, opgeknipt bij kunstwerken/aansluitingen en in beheersbare segmenten.
- `hydroobject_verbinding`: gerichte topologische verbindingen (`van_segment`, `naar_segment`, op basis van de tekenrichting van hydroobjecten) tussen de watergangsegmenten.

`afwateringseenheden.gpkg` bevat de laag `afvoergebiedaanvoergebied` met Polygon-
en MultiPolygon-geometrie, elk gekoppeld aan het hydroobject_segment waarnaar
het oppervlak afwatert.

De standaardproject-CRS is `EPSG:28992`. Elke laag heeft tevens een voorgedefinieerde stijldefinitie die automatisch wordt herkend door QGIS.

## Aandachtspunten en beperkingen

Secundaire objecten gelden als verbonden wanneer hun volledige geometrie binnen
de ingestelde tolerantie (standaard 2 m) van een primair of secundair object
ligt. Tegels zonder segmentcellen worden overgeslagen. Als een gebied vanaf de
buffergrens de kerntile bereikt, meldt Waterlagen de tile als randprobleem.
Die melding betreft de situatie vóór het aanvullen vanuit buurtegels.
Controleer de resterende gaten na het samenvoegen; automatisch herberekenen
met een grotere buffer maakt geen deel uit van de workflow.

## Zelf produceren

Zie voor het zelf produceren het werkende voorbeeld voor waterschap Aa en Maas onder [zelf produceren](../produceren/afwateringseenheden.md).

Zie voor het gebruik van de onderliggende Python-functies de [API-referentie](../reference/afwateringseenheden.md).
