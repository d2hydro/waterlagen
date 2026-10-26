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
| [Rijkswateren](../bronlagen/rijkswateren.md) | Waterlopen van Rijkswaterstaat. |
| [AHN](../bronlagen/ahn.md) | Maaiveldhoogte voor het afleiden van afstroomrichtingen en afwateringseenheden. |
| [Bestuurlijke gebieden](../bronlagen/bestuurlijke-gebieden.md) | Begrenzing tot Nederland. |

## Werkwijze

Op basis van een geselecteerde gebiedsgrens (waterschap, nederland, of iets anders) worden met overlappende vierkante tegels, bestaande uit een kerntegel + buffer afwateringseenheden afgeleidt. Wanneer alle tegels zijn bewerkt worden de resultaten samengevoegd tot gebiedsdekkende set polygonen. Deze worden niet afgesneden op de gebiedsgrens; een afvoergebied houdt zich immers niet aan, veelal administratieve, grenzen.

De stappen worden hieronder 1 voor 1 uitgelegd.

### Voorbewerken watersysteem

- Primaire, secundaire en tertiaire waterlopen worden geselecteerd voor de tegels en hun buffers.
- Primaire waterlopen worden opgeknipt bij verbindingspunten en op maximaal 500 m lengte.
- Gemalen en stuwen blijven herkenbaar aan hun brongegevens.
- `van_segment` en `naar_segment` verbinden de segmenten volgens de tekenrichting van de waterlopen.
- Secundaire waterlopen worden verdeeld in waterlopen met en zonder verbinding met het primaire watersysteem.

Een **afwateringsdoel** is een primair segment waaraan een afwateringseenheid wordt toegewezen.

| Gebiedsselectie | Beheerders van afwateringsdoelen en verbindingspunten |
| --- | --- |
| Eén waterschap | Alleen het gekozen waterschap |
| Eén waterschap, met overige waterschappen | Alle geselecteerde waterschappen; geen RWS |
| Geen waterschapselectie | Alle geselecteerde beheerders, inclusief RWS |

Waterlopen van omliggende beheerders blijven beschikbaar om de afstroming te bepalen.
Secundaire en tertiaire waterlopen zijn zelf geen afwateringsdoelen.

### Waterlopen en duikers inbranden

Standaard worden de geselecteerde waterlopen en duikers uit HYDAMO en Rijkswateren gebruikt.
Niet elk object wordt ingebrand: daarvoor gelden de regels hieronder.

- **Een duiker die alleen primaire waterlopen met elkaar verbindt, wordt niet ingebrand.**
- Inbranden past de hoogte in het reken-DEM aan om de afstroming te sturen.
- Voor waterlopen en duikers wordt de hoogte verlaagd.
- De verlagingen zijn geen werkelijke waterbodemhoogtes.
- Verbindingen worden bepaald op een raster met cellen van 2 × 2 m. Ook cellen die elkaar alleen op een hoek raken, gelden als verbonden.

| Waterloop of duiker | Verlaging in de standaardproductie |
| --- | ---: |
| Primaire waterloop buiten de gekoppelde duikertrajecten | 200 m |
| Secundaire HYDAMO-waterloop met een route naar primair | 100 m |
| HYDAMO-duiker secundair–primair of secundair–secundair, met een route naar primair | 100 m |
| Secundaire HYDAMO-waterloop zonder route naar primair; tertiaire HYDAMO-waterloop | 10 m |
| Andere aangesloten HYDAMO-duiker, behalve primair–primair | 10 m |
| Duiker die alleen primair met primair verbindt | Geen |
| Duiker met minder dan twee herkende aansluitingen | Geen; naar controle |

- Voor de verlaging van 100 m telt alleen een route via primaire en secundaire HYDAMO-waterlopen en geschikte HYDAMO-duikers.
- Duikertrajecten zijn geen afwateringsdoel. Een afzonderlijke primaire waterloop die een duiker kruist, kan wel een doel blijven.
- Een rastercel heeft één stroomrichting. Waterlopen die op verschillende hoogtes kruisen, blijven daardoor niet automatisch gescheiden.

### Optionele brandlagen

Naast HYDAMO en Rijkswateren kunt u **optionele brandlagen** toevoegen via de TOML.
BGT, OSM en TOP10NL doen alleen mee als ze daarin zijn opgenomen.

| Optionele brandlaag | Gebruik |
| --- | --- |
| Waterlopen uit BGT, OSM of TOP10NL | Verlagen met de ingestelde brandwaarde. |
| Duikers uit BGT of OSM | Verlagen als de duiker voldoet aan de aansluitregels hierboven. |
| Wegen of eigen correcties | Verhogen of verlagen met de ingestelde brandwaarde. |

- De `brandwaarde` is de hoogteaanpassing in meters: negatief verlaagt, positief verhoogt.
- Optionele brandlagen voegen geen afwateringsdoelen toe.
- Ze geven een losliggend HYDAMO-stelsel geen verlaging van 100 m.

Bij overlap:

- HYDAMO-waterlopen en -duikers houden voorrang op optionele brandlagen.
- Bij dubbele duikers gaat HYDAMO voor BGT, daarna OSM.
- Tussen optionele brandlagen wint de hoogste prioriteit.
- Bij gelijke prioriteit wint de grootste hoogteaanpassing: bijvoorbeeld −4 m boven −1 m.
- Verhogen en verlagen in dezelfde cel bij gelijke prioriteit geeft een fout, ook als een andere laag voorrang heeft.

Zie de [productie-instructies](../produceren/afwateringseenheden.md#optionele-brandlagen) voor de TOML-instellingen.

### Afleiden afwateringseenheden

Op basis van het [AHN-DTM](../bronlagen/ahn.md) en het hierboven genoemde watersysteem worden de volgende stappen uitgevoerd:

- Het DTM (0,5 × 0,5 meter) wordt geschaald ingelezen op 2 × 2 meter (instelbaar) en binnen de brondekking dichtgeïnterpoleerd.
- Waterlopen, duikers en optionele brandlagen worden ingebrand volgens de regels hierboven.
- Geschikte primaire segmenten worden als afwateringsdoelen op hetzelfde raster gezet.
- De stroomrichting (LDD) wordt per cel berekend. Laagtes worden tot maximaal 50 m opgevuld.
- Cellen die via de LDD een afwateringsdoel bereiken, krijgen het nummer van dat segment.
- Het raster wordt omgezet naar vlakken. `segment_id` koppelt elk vlak aan het bijbehorende segment.
- Zonder route naar een afwateringsdoel blijft een gebied niet toegewezen.

Grote gebieden kunnen in gebufferde tegels worden berekend:

- De standaardproductie gebruikt kerntegels van 10 × 10 km.
- Per kerntile wordt de berekening uitgevoerd op de tile inclusief een buffer. De standaardbuffer is 2 km, zodat afstroming van buiten de kerntile kan worden meegenomen.
- Alleen afwateringseenheden die niet tot aan de buitenste rekenrand van de buffer reiken, worden teruggeknipt naar de kerntile en meegenomen in het resultaat.
- De bruikbare resultaten worden per `segment_id` samengevoegd. De standaardproductie knipt ze niet af op de gekozen gebiedsgrens.
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

- **Duikeraansluitingen**: controleer deze; ze worden nog niet in alle situaties goed verwerkt.
- **Verbinding van secundaire objecten**: een secundair object geldt als verbonden wanneer de volledige geometrie binnen de ingestelde afstand van een primair of secundair object ligt. Deze tolerantie is standaard 2 meter.
- **Overgeslagen tegels**: tegels worden overgeslagen als geen enkele rastercel met een hydroobjectsegment een geldige DEM-hoogte heeft. Dit gebeurt ook wanneer alle segmenten buiten de brondekking of de landsgrens liggen. De voorbereide rasters blijven beschikbaar voor hergebruik.
- **Randproblemen**: Waterlagen meldt een randprobleem wanneer een berekend afwateringsgebied zowel de buitenste buffergrens als de kern van de tegel raakt. Deze melding wordt gedaan vóór het aanvullen van gaten vanuit buurtegels en betekent dus niet automatisch dat er in het eindresultaat een gat overblijft.
- **Controle na samenvoegen**: controleer het eindresultaat op resterende gaten. Opnieuw berekenen met een grotere buffer kan gaten door randproblemen verminderen, maar gebeurt niet automatisch.

## Zelf produceren

Zie voor het zelf produceren het werkende voorbeeld voor waterschap Aa en Maas onder [zelf produceren](../produceren/afwateringseenheden.md).

Zie voor het gebruik van de onderliggende Python-functies de [API-referentie](../reference/afwateringseenheden.md).
