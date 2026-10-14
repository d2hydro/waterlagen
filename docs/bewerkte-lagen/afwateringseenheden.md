---
editorial_status: human
---

# Afwateringseenheden

## Doel

Het berekenen van `afvoergebieden` gekoppeld aan `hydroobjecten`.

## Bronlagen

| Bron | Gebruik |
| --- | --- |
| [GKW HYDAMO](../bronlagen/hydamo.md) | Hydroobjecten en verbindingspunten voor het watersysteem. |
| [AHN](../bronlagen/ahn.md) | Maaiveldhoogte voor het afleiden van afstroomrichtingen en afwateringseenheden. |
| [Bestuurlijke gebieden](../bronlagen/bestuurlijke-gebieden.md) | Begrenzing tot Nederland. |

## Werkwijze

Op basis van een geselecteerde gebiedsgrens (waterschap, nederland, of iets anders) worden met overlappende vierkante tegels, bestaande uit een kerntegel + buffer afwateringseenheden afgeleidt. Wanneer alle tegels zijn bewerkt worden de resultaten samengevoegd tot gebiedsdekkende set polygonen. Deze worden niet afgesneden op de gebiedsgrens; een afvoergebied houdt zich immers niet aan, veelal administratieve, grenzen.

De stappen worden hieronder 1 voor 1 uitgelegd.

### Voorbewerken watersysteem

Vanuit de geleverde (Hy)DAMO-set worden:

- `primaire` en `secundaire` `hydroobjecten` en relevante `verbindingspunten` (bijvoorbeeld `gemalen` en `stuwen`) uitgelezen. De standaardproductie selecteert ruimtelijk met de benodigde tegelcontext en gebruikt geen aanvullend waterbeheerderfilter. Lagere Python-functies ondersteunen zo nodig een expliciet beheerderfilter.
- `Primaire` hydroobjecten worden bij de relevante `verbindingspunten` en op een maximale lengte (standaard 500 meter) opgesplitst naar `hydroobject-segmenten`.
- `Verbindingspunten` vormen een gericht netwerk, waarbij `van_segment` en `naar_segment` de richting vormen. Van opgegeven punten (`stuwen`, `gemalen`, etc.) worden tevens de oorspronkelijke eigenschappen bewaard, zodat deze herkenbaar blijven.
- `Secundaire hydroobjecten` worden opgesplitst in een set die wél en een set die níet verbonden is met de `primaire hydroobjecten`.

### Afleiden afwateringseenheden

Op basis van het [AHN-DTM](../bronlagen/ahn.md) en het hierboven genoemde watersysteem worden de volgende stappen uitgevoerd:

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
- Tegels zonder `hydroobject-segmenten` op geldige DEM-cellen worden overgeslagen. Wanneer een afwateringseenheid vanaf de buffergrens de kerntile bereikt, wordt de tegel gemeld als randprobleem.

### Samenvoegen
Na de berekening worden de resultaten van alle tegels samengevoegd tot één set afwateringseenheden voor het interessegebied. Losse lijn- en puntresten worden verwijderd. Polygonen die de buitenste tegelrand raken, worden niet meegenomen.

Gaten in binnen een kerntegel worden waar mogelijk aangevuld met polygonen uit naburige tegels (tegels overlappen door de buffer). Hiervoor wordt geen nieuwe LDD berekend. Als meerdere buurpolygonen geschikt zijn, krijgt de polygoon die het gat het meest bedekt voorrang. Bij gelijke dekking wordt gekozen voor de polygoon met de grootste afstand tot de tegelrand (kerntegel plus buffer). Is ook die afstand gelijk, dan bepaalt het tegel-ID de keuze.

Alleen ontbrekende delen worden aangevuld; bestaande toewijzingen blijven behouden. Zonder geschikte buurpolygoon blijft een gat open. Door de tegels opnieuw te berekenen met een grotere buffer kunnen meer afwateringseenheden behouden blijven, waardoor minder gaten ontstaan.

## Uitvoer
De volledige afleiding van afwateringseenheden bevat een `watersysteem.gpkg` en `afwateringseenheden.pgkg`.

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
Bij het berekenen van afwateringseenheden zijn wij de volgende aandachtspunten en beperkingen tegengekomen:
- **Verbinding van secundaire objecten**: een secundair object geldt als verbonden wanneer de volledige geometrie binnen de ingestelde afstand van een primair of secundair object ligt. Deze tolerantie is standaard 2 meter.
- **Overgeslagen tegels**: tegels worden overgeslagen als geen enkele rastercel met een hydroobjectsegment een geldige DEM-hoogte heeft. Dit gebeurt ook wanneer alle segmenten buiten de brondekking of de landsgrens liggen. De voorbereide rasters blijven beschikbaar voor hergebruik.
- **Randproblemen**: Waterlagen meldt een randprobleem wanneer een berekend afwateringsgebied zowel de buitenste buffergrens als de kern van de tegel raakt. Deze melding wordt gedaan vóór het aanvullen van gaten vanuit buurtegels en betekent dus niet automatisch dat er in het eindresultaat een gat overblijft.
- **Controle na samenvoegen**: controleer het eindresultaat op resterende gaten. Opnieuw berekenen met een grotere buffer kan gaten door randproblemen verminderen, maar gebeurt niet automatisch.

## Zelf produceren

Zie voor het zelf produceren het werkende voorbeeld voor waterschap Aa en Maas onder [zelf produceren](../produceren/afwateringseenheden.md).

Zie voor het gebruik van de onderliggende Python-functies de [API-referentie](../reference/afwateringseenheden.md).
