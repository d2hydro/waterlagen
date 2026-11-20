---
editorial_status: human
---

# Afwateringseenheden

## Doel

Een afwateringseenheid is een gebied dat volgens de berekende afstroming naar
hetzelfde primaire waterloopsegment afwatert. Deze gebieden worden bepaald met
maaiveldhoogtes, waterlopen en duikers. Het resultaat is een modelmatige afbakening.

<span id="zelf-produceren"></span>

[Afwateringseenheden maken](../produceren/afwateringseenheden.md){ .md-button .md-button--primary }
[API-referentie](../reference/afwateringseenheden.md){ .meerlink }

## Uitvoer

Het eindresultaat staat in `afwateringseenheden.gpkg`. De bijbehorende waterlopen en segmenten staan in `watersysteem.gpkg`.

`afwateringseenheden.gpkg` bevat de laag `afvoergebiedaanvoergebied` met Polygon-
en MultiPolygon-geometrie. Koppel het `segment_id` van een vlak aan hetzelfde
`segment_id` in `watersysteem.gpkg`, laag `hydroobject_segment`, om het
bijbehorende waterloopsegment te vinden. Deze koppeling geldt **binnen dezelfde run**.

??? info "Kaartlagen en velden in de GeoPackages"

    `watersysteem.gpkg` bevat de volgende lagen:

    - `hydroobject_primair`: primaire waterloopdelen uit HYDAMO en Rijkswateren die voor inbranding zijn geselecteerd.
    - `hydroobject_secundair`: secundaire watergangen die ruimtelijk verbonden zijn met het primaire systeem.
    - `hydroobject_secundair_niet_verbonden`: secundaire watergangen zonder ruimtelijke verbinding met het primaire systeem.
    - `hydroobject_segment`: primaire waterlopen van de geselecteerde doelbeheerders, opgeknipt bij aansluitingen en duikertrajecten en op maximaal 500 m lengte.
    - `hydroobject_verbinding`: gerichte verbindingen tussen de waterloopsegmenten.

    | Laag | Veld | Betekenis |
    | --- | --- | --- |
    | `afvoergebiedaanvoergebied`, `hydroobject_segment` | `segment_id` | Nummer dat het afwateringsvlak en het bijbehorende segment verbindt. |
    | `hydroobject_segment`, `hydroobject_primair` | `brandgeschikt` | Het segment of waterloopdeel mag worden ingebrand. |
    | `hydroobject_segment` | `afwateringsdoel` | Geeft aan of het segment als afwateringsdoel is toegelaten. |
    | `hydroobject_verbinding` | `van_segment`, `naar_segment` | Segmentnummers aan weerszijden van een verbinding, volgens de tekenrichting van de waterlopen. |
    | `hydroobject_verbinding` | `kunstwerk_…` | Bron-ID, code, naam en beheerder van een gekoppelde stuw of gemaal; anders leeg. |

    Het standaardcoördinatenstelsel is `EPSG:28992`. Waar een QGIS-stijl beschikbaar
    is, wordt die in het GeoPackage opgenomen.

## Werkwijze

Primaire waterloopsegmenten dienen als afwateringsdoel. De stroomrichting wordt berekend op een hoogteraster met ingebrande waterlopen en duikers. Cellen die hetzelfde segment bereiken vormen samen een afwateringseenheid. Waar geen route naar een doel bestaat, blijft het gebied niet toegewezen.

<span id="voorbewerken-watersysteem-uit-hydamo-en-rijkswateren"></span>

??? info "Waterlopen en afwateringsdoelen selecteren"

    - Primaire, secundaire en tertiaire waterlopen uit HyDAMO en RWS worden geselecteerd voor de tegels met buffers.
    - Primaire waterlopen worden opgeknipt bij verbindingspunten en op maximaal 500 m lengte.

    Waterlopen van Rijkswaterstaat worden uit de Rijkswaterenbron gehaald; GKW-waterlopen met beheerderscode 80 worden daarom niet gebruikt.

    <span id="verbinding-van-secundaire-waterlopen-uit-hydamo"></span>

    **Verbinding van secundaire waterlopen uit HyDAMO**

    - Secundaire waterlopen uit HyDAMO worden gegroepeerd als ze binnen 2 m van elkaar liggen.
    - Een groep is verbonden als een waterloop binnen 2 m van een primaire waterloop ligt.
    - Die primaire waterloop mag van een andere beheerder zijn.

    Dit bepaalt welke secundaire waterlopen als verbonden of niet verbonden worden opgenomen in de uitvoer.

    <span id="afwateringsdoelen"></span>

    **Afwateringsdoelen**

    Een **afwateringsdoel** is een primair segment dat als doel is toegelaten. Zodra het segment minimaal één geldige doelcel krijgt bij rasterisatie, ontstaat een afwateringseenheid.

    Bij selectie van één waterschap worden alleen primaire segmenten van dat waterschap als afwateringsdoel gebruikt. Met --overige-waterschappen tellen ook primaire segmenten van andere waterschappen mee. Zonder waterschapselectie kunnen ook hoofdwaterlopen van Rijkswaterstaat als afwateringsdoel dienen.

    Secundaire en tertiaire waterlopen zijn zelf geen afwateringsdoelen.

    Bij korte parallelle routes met ieder een eigen kunstwerk (stuw, gemaal, duiker, sifon of hevel) worden de interne hydroobjecten uitgesloten als afwateringsdoel. Dit geldt alleen als iedere volledige route maximaal 100 m lang is.

    De maximale routelengte is instelbaar. Met 0 wordt de uitsluitregel uitgeschakeld.

<span id="waterlopen-en-duikers-inbranden"></span>

??? info "Waterlopen en duikers inbranden"

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

??? info "Extra brandlagen en voorrang"

    <span id="optionele-brandlagen"></span>

    Elke gekozen brandlaag past de rekenhoogte rechtstreeks aan. Dat geldt voor [BGT](../bronlagen/bgt.md), [OSM](../bronlagen/osm-waterlopen.md), [TOP10NL](../bronlagen/top10nl.md) en eigen GeoPackages. Ook een opgegeven duiker zonder aansluiting op een waterloop wordt ingebrand. Aanvullende lagen bepalen geen netwerkverbindingen of afwateringsdoelen.

    De `brandwaarde` is een hoogteverandering in meters. Negatief verlaagt, positief verhoogt. Lijnen houden hun breedte van één rasterlijn. Bij vlakken tellen alle geraakte cellen mee. Buiten de DEM-dekking blijft de hoogte NoData.

    Bij overlap gelden deze regels:

    - Actieve inbranding uit HyDAMO of Rijkswateren heeft voorrang.
    - Tussen aanvullende lagen wint de hoogste `prioriteit`. Bij gelijke prioriteit wint de grootste absolute hoogteverandering.
    - Verhogen én verlagen in dezelfde cel bij gelijke prioriteit geeft een fout, ook als een derde laag voorrang heeft.
    - Per cel geldt één waarde. Een brandwaarde van nul kan een lagere prioriteit blokkeren.

    Zie [brandlagen instellen](../produceren/afwateringseenheden.md#test-met-eigen-gebied-en-brandlagen).

<span id="afleiden-afwateringseenheden"></span>
<span id="aandachtspunten-en-beperkingen"></span>


??? info "Van stroomrichting naar vlakken"

    - Het AHN-DTM van 0,5 × 0,5 m wordt omgezet naar cellen van 2 × 2 m. Ontbrekende hoogtes worden binnen de brondekking en landsgrens aangevuld.
    - Waterlopen, duikers en optionele brandlagen worden ingebrand volgens de regels hierboven.
    - Geschikte primaire segmenten worden als afwateringsdoelen op hetzelfde raster gezet.
    - De stroomrichting (LDD) wordt per cel berekend. Laagtes worden tot maximaal 50 m opgevuld.
    - Cellen die via de LDD een afwateringsdoel bereiken, krijgen het nummer van dat segment.
    - Het raster wordt omgezet naar vlakken, gekoppeld aan het bijbehorende segment.
    - Zonder route naar een afwateringsdoel blijft een gebied niet toegewezen.

<span id="tegels-buffers-en-samenvoegen"></span>
<span id="samenvoegen"></span>


??? info "Rekenen langs tegelranden"

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

## Bronlagen

Waterlagen gebruikt het [AHN](../bronlagen/ahn.md), hydroobjecten en kunstwerken uit [HyDAMO via GKW](../bronlagen/hydamo.md) en [Rijkswateren](../bronlagen/rijkswateren.md), en [bestuurlijke gebieden](../bronlagen/bestuurlijke-gebieden.md). Zie ook [extra brandlagen en voorrang](#optionele-brandlagen).
