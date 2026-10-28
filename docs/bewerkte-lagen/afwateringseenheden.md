---
editorial_status: human
---

# Afwateringseenheden

## Doel

Een afwateringseenheid is een gebied dat volgens de berekende afstroming naar
hetzelfde primaire waterloopsegment afwatert. Deze gebieden worden bepaald met
maaiveldhoogtes, waterlopen en duikers. Het resultaat is een modelmatige afbakening.

## Bronlagen

Waterlagen gebruikt het [AHN](../bronlagen/ahn.md), hydroobjecten en kunstwerken uit [HyDAMO via GKW](../bronlagen/hydamo.md) en [Rijkswateren](../bronlagen/rijkswateren.md), en [bestuurlijke gebieden](../bronlagen/bestuurlijke-gebieden.md). Optionele brandlagen worden hieronder beschreven.

## Werkwijze

### Voorbewerken watersysteem uit HyDAMO en Rijkswateren

- Primaire, secundaire en tertiaire waterlopen uit HyDAMO en RWS worden geselecteerd voor de tegels met buffers.
- Primaire waterlopen worden opgeknipt bij verbindingspunten en op maximaal 500 m lengte.

Waterlopen van Rijkswaterstaat worden uit de Rijkswaterenbron gehaald; GKW-waterlopen met beheerderscode 80 worden daarom niet gebruikt.

#### Verbinding van secundaire waterlopen uit HyDAMO

- Secundaire waterlopen uit HyDAMO worden gegroepeerd als ze binnen 2 m van elkaar liggen.
- Een groep is verbonden als een waterloop binnen 2 m van een primaire waterloop ligt.
- Die primaire waterloop mag van een andere beheerder zijn.

Dit bepaalt welke secundaire waterlopen als verbonden of niet verbonden worden opgenomen in de uitvoer.

#### Afwateringsdoelen

Een **afwateringsdoel** is een primair segment waaraan een afwateringseenheid wordt toegewezen.

Bij selectie van één waterschap worden alleen primaire segmenten van dat waterschap als afwateringsdoel gebruikt. Met --overige-waterschappen tellen ook primaire segmenten van andere waterschappen mee. Zonder waterschapselectie kunnen ook hoofdwaterlopen van Rijkswaterstaat als afwateringsdoel dienen.

Secundaire en tertiaire waterlopen zijn zelf geen afwateringsdoelen.

### Waterlopen en duikers inbranden

Bij het inbranden wordt het rekenhoogtemodel verlaagd langs waterlopen en geschikte duikers uit HyDAMO en de Rijkswaterenbron. Deze kunstmatige verlagingen sturen de berekende afstroming; ze stellen geen werkelijke waterbodemhoogtes voor.

Secundaire waterlopen krijgen een grotere verlaging als ze via andere secundaire waterlopen en geschikte duikers verbonden zijn met een primaire waterloop. Aanvullende brandlagen, zoals BGT, TOP10NL en OSM, tellen niet mee bij het bepalen van deze verbinding.

Verbindingen worden bepaald op een raster met cellen van 2 × 2 m. Ook cellen
die elkaar alleen op een hoek raken, gelden als verbonden.

| Waterloop of duiker | Verlaging in de standaardproductie |
| --- | ---: |
| Primaire waterloop buiten de gekoppelde duikertrajecten | 200 m |
| Secundaire waterloop met een route naar primair | 100 m |
| Duiker secundair–primair of secundair–secundair, met een route naar primair | 100 m |
| Secundaire waterloop zonder route naar primair; tertiaire waterloop | 10 m |
| Andere aangesloten duiker, behalve primair–primair | 10 m |
| Duiker die alleen primair met primair verbindt | Geen |
| Duiker met minder dan twee herkende aansluitingen | Geen; naar controle |

- Duikertrajecten zijn geen afwateringsdoel. Een afzonderlijke primaire waterloop die een duiker kruist, kan wel een doel blijven.
- Een rastercel heeft één stroomrichting. Waterlopen die op verschillende hoogtes kruisen, blijven daardoor niet automatisch gescheiden.

### Optionele brandlagen

**Optionele brandlagen** passen het rekenhoogtemodel aanvullend aan.
BGT, OSM, TOP10NL en eigen correcties worden alleen gebruikt als ze zijn ingesteld.

| Optionele brandlaag | Gebruik |
| --- | --- |
| [BGT](../bronlagen/bgt.md), [OSM](../bronlagen/osm-waterlopen.md) of [TOP10NL](../bronlagen/top10nl.md): waterlopen | Verlagen met de ingestelde brandwaarde. |
| BGT- of OSM-duikers | Verlagen als de duiker voldoet aan de aansluitregels hierboven. |
| Wegen of eigen correcties | Verhogen of verlagen met de ingestelde brandwaarde. |

Optionele waterlagen tellen mee bij ontbrekende duikeraansluitingen. Een duiker
die volgens HYDAMO of Rijkswateren uitsluitend primaire waterlopen verbindt,
blijft uitgesloten van inbranding. Bij duikervlakken tellen aansluitende
lijnuiteinden en contact met watervlakken; een doorgaande waterlijn die het
duikervlak alleen kruist, geldt niet als twee aansluitingen.

- De `brandwaarde` is de hoogteaanpassing in meters: negatief verlaagt, positief verhoogt.
- Optionele brandlagen voegen geen afwateringsdoelen toe.
- Lijnen krijgen geen extra breedte. Bij vlakken doen alle geraakte rastercellen mee.
- Cellen zonder DEM-hoogte buiten de dekking blijven NoData.

Bij overlap:

- Waterlopen en geschikte duikers uit HyDAMO en de Rijkswaterenbron hebben voorrang op optionele brandlagen.
- Als dezelfde duiker in meerdere bronnen voorkomt, gaat de duiker uit HyDAMO of de Rijkswaterenbron voor die uit andere optionele brandlagen, zoals BGT.
- Tussen optionele brandlagen wint de hoogste prioriteit.
- Bij gelijke prioriteit wint de grootste absolute hoogteaanpassing: een verlaging van 4 m gaat vóór een verlaging van 1 m.
- Verhogen en verlagen in dezelfde cel bij gelijke prioriteit geeft een fout, ook als een andere laag voorrang heeft.
- Hoogteaanpassingen worden niet opgeteld. Brandwaarde `0` verandert de hoogte niet, maar kan een laag met lagere prioriteit tegenhouden.

Zie de [productie-instructies](../produceren/afwateringseenheden.md#optionele-brandlagen) voor de TOML-instellingen.

<span id="aandachtspunten-en-beperkingen"></span>

### Afleiden afwateringseenheden

- Het AHN-DTM van 0,5 × 0,5 m wordt omgezet naar cellen van 2 × 2 m. Ontbrekende hoogtes worden binnen de brondekking en landsgrens aangevuld.
- Waterlopen, duikers en optionele brandlagen worden ingebrand volgens de regels hierboven.
- Geschikte primaire segmenten worden als afwateringsdoelen op hetzelfde raster gezet.
- De stroomrichting (LDD) wordt per cel berekend. Laagtes worden tot maximaal 50 m opgevuld.
- Cellen die via de LDD een afwateringsdoel bereiken, krijgen het nummer van dat segment.
- Het raster wordt omgezet naar vlakken, gekoppeld aan het bijbehorende segment.
- Zonder route naar een afwateringsdoel blijft een gebied niet toegewezen.

<span id="samenvoegen"></span>

### Tegels, buffers en samenvoegen

In de standaardproductie selecteert het gekozen gebied kerntegels van 10 × 10 km.
Rond elke kerntegel ligt een buffer van 2 km: het rekengebied is daardoor
14 × 14 km. Zo telt ook afstroming vanuit de omgeving mee. Tegels zonder afwateringsdoel op geldige
DEM-cellen worden overgeslagen.

Vlakken die de buitenrand van het rekengebied bereiken, worden uitgesloten,
met een veiligheidsmarge van één rastercel. **De kerntegelgrens is niet de
afkeurgrens.** Bruikbare vlakken worden op de kerntegel geknipt en per
waterloopsegment samengevoegd. Losse lijn- en puntresten vervallen. De
standaardproductie knipt de uitvoer niet op de gekozen gebiedsgrens.

Gaten binnen een kerntegel worden waar mogelijk aangevuld vanuit de berekende
vlakken van buurtegels, zonder nieuwe stroomrichtingen te berekenen. Alleen
ontbrekende delen worden toegevoegd. Zonder geschikte aanvulling blijft een gat open.
De technische selectie staat
bij [randfilter en aanvulling](../reference/afwateringseenheden.md#randfilter-en-aanvulling).

Een randprobleem wordt gemeld als een uitgesloten vlak ook de kerntegel raakt.
Deze melding geldt vóór de aanvulling uit buurtegels en betekent niet automatisch
dat het eindresultaat een gat bevat. Een grotere rekenbuffer kan randproblemen
verminderen, maar vraagt een nieuwe berekening via de
[Python-API](../reference/afwateringseenheden.md#rekenbuffer-instellen).

## Uitvoer

Het eindresultaat staat in `afwateringseenheden.gpkg`. De bijbehorende waterlopen en segmenten staan in `watersysteem.gpkg`.

`watersysteem.gpkg` bevat de volgende lagen:

- `hydroobject_primair`: primaire waterloopdelen uit HYDAMO en Rijkswateren die voor inbranding zijn geselecteerd.
- `hydroobject_secundair`: secundaire watergangen die ruimtelijk verbonden zijn met het primaire systeem.
- `hydroobject_secundair_niet_verbonden`: secundaire watergangen zonder ruimtelijke verbinding met het primaire systeem.
- `hydroobject_segment`: primaire waterlopen van de geselecteerde doelbeheerders, opgeknipt bij aansluitingen en duikertrajecten en op maximaal 500 m lengte.
- `hydroobject_verbinding`: gerichte verbindingen tussen de waterloopsegmenten.

`afwateringseenheden.gpkg` bevat de laag `afvoergebiedaanvoergebied` met Polygon-
en MultiPolygon-geometrie. Koppel het `segment_id` van een vlak aan hetzelfde
`segment_id` in `watersysteem.gpkg`, laag `hydroobject_segment`, om het
bijbehorende waterloopsegment te vinden. Deze koppeling geldt **binnen dezelfde run**.

| Laag | Veld | Betekenis |
| --- | --- | --- |
| `afvoergebiedaanvoergebied`, `hydroobject_segment` | `segment_id` | Nummer dat het afwateringsvlak en het bijbehorende segment verbindt. |
| `hydroobject_segment`, `hydroobject_primair` | `brandgeschikt` | Het segment of waterloopdeel mag worden ingebrand. |
| `hydroobject_segment`, `hydroobject_primair` | `doelgeschikt` | Het waterloopdeel is geschikt als doel; alleen de geselecteerde segmenten kunnen daadwerkelijk een toewijzing krijgen. |
| `hydroobject_verbinding` | `van_segment`, `naar_segment` | Segmentnummers aan weerszijden van een verbinding, volgens de tekenrichting van de waterlopen. |
| `hydroobject_verbinding` | `kunstwerk_…` | Bron-ID, code, naam en beheerder van een gekoppelde stuw of gemaal; anders leeg. |

Zie de [productiehandleiding](../produceren/afwateringseenheden.md#uitvoer-en-hervatten) voor bestandslocaties, controlebestanden en hervatten.

Het standaardcoördinatenstelsel is `EPSG:28992`. Waar een QGIS-stijl beschikbaar
is, wordt die in het GeoPackage opgenomen.

## Zelf produceren

Volg de [productiehandleiding](../produceren/afwateringseenheden.md) voor
uitvoering en controle. Voor eigen Python-workflows is er de
[API-referentie](../reference/afwateringseenheden.md).
