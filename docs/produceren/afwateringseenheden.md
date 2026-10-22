---
editorial_status: ai
---

# Afwateringseenheden produceren

Deze productie ondersteunt Nederland, een waterschapscode en gedeelde gebieden
zoals Alkmaar. Volg eerst [Installatie](installatie.md); het releasepakket bevat
PCRaster. Vanuit de repository gebruikt u de omgeving `afwateringseenheden`.

## Starten

```console
pixi run --locked afwateringseenheden --area alkmaar --workers 2
pixi run --locked afwateringseenheden --waterbeheercode 38 --workers 2
```

Zonder gebiedsoptie wordt **Nederland** verwerkt. Een onbekende waterschapscode
geeft een fout voordat AHN en HYDAMO worden opgehaald. Kies `--workers 1` bij
weinig werkgeheugen. De overige [gedeelde CLI-opties](cli.md) regelen opslag,
bronvernieuwing, offline gebruik en hervatten.

## Workflow

### Eigen gebied met brandlagen

1. Zet de gewenste bestanden en lagen in de [brandlagen-TOML](#toml-configuratie).
2. Start het [PowerShell-voorbeeld](voorbeelden/afwateringseenheden_issue63.ps1):

   ```powershell
   .\docs\produceren\voorbeelden\afwateringseenheden_issue63.ps1 -BrandlagenConfig '.\invoer\brandlagen.toml'
   ```

3. Open `afwateringseenheden.gpkg` uit de resultaatmap in QGIS.

Het voorbeeld selecteert 1 x 1 km rond RD-punt `(184785, 392554)`.
Geef voor een ander gebied `-Xmin`, `-Ymin`, `-Xmax` en `-Ymax` mee.
Zie [gebiedsselectie](cli.md#eigen-rechthoekig-gebied).

### Verwerking

1. Het gebied selecteert volledige tegelkernen van 10 x 10 km.
2. HYDAMO en Rijkswateren worden opgehaald of hergebruikt. De invoer wordt
   gecontroleerd voordat het AHN wordt voorbereid.
3. Waterlopen en AHN worden geselecteerd voor de tegels en hun buffers.
   Geselecteerde waterlopen worden niet op de gebiedsgrens afgeknipt.
4. De productie berekent de tegels en voegt de bruikbare resultaten samen.
   De gebiedsgrens knipt het resultaat niet af.

De tegelbuffer is 2000 m, de rasterresolutie 2 m, de inbranddiepte voor
secundaire waterlopen 100 m en de maximale opvuldiepte 50 m. De vaste seed is
12345. De landsgrens begrenst de AHN-interpolatie tot Nederland. Dit staat los
van de gekozen gebiedsgrens als invoerselectie.
De betekenis en beperkingen staan bij
[Afwateringseenheden](../bewerkte-lagen/afwateringseenheden.md).

## Doelmodi en bronnen

Een afwateringsdoel is een primair waterloopsegment waaraan een gebied wordt toegewezen.
Andere waterlopen helpen de afstroming te bepalen.

| Gebiedsselectie | Afwateringsdoelen |
| --- | --- |
| Waterschapscode | Alleen het gekozen waterschap |
| Waterschapscode met `--overige-waterschappen` | Alle geselecteerde waterschappen |
| Zonder waterschapscode | Alle geselecteerde waterschappen en RWS |

Waterlopen van omliggende beheerders blijven meedoen bij de inbranding.
Secundaire waterlopen zijn geen afwateringsdoelen.

RWS-waterlopen komen uit de [Rijkswaterenbron](../bronlagen/rijkswateren.md).
GKW-waterlopen met code `80` worden niet gebruikt.
Met `--rijkswateren-url` kunt u een andere bronlocatie instellen.

```console
pixi run --environment afwateringseenheden afwateringseenheden --waterbeheercode 38 --overige-waterschappen
pixi run --environment afwateringseenheden afwateringseenheden --waterbeheercode 38 --eigen-hydamo eigen.gpkg
```

### Eigen levering

`--eigen-hydamo` vervangt de GKW-gegevens van het gekozen waterschap.
GKW blijft beschikbaar voor de omgeving.

- Verplicht: `hydroobject`, `gemaal`, `stuw` en `duikersifonhevel`.
- Kunstwerklagen mogen leeg zijn. Ontbrekende gegevens worden niet uit GKW aangevuld.
- Elk object moet een geldig `nen3610id` van het gekozen waterschap hebben.
- Het coördinatenstelsel (CRS) en de waterloopcategorie moeten bekend zijn.

De categorie staat in `categorieoppwaterlichaam` of `categorieoppervlaktewater`.
`primair`, `secundair` en `tertiair` doen mee; `overig` niet.
GKW-waterlopen zonder categorie komen in `controle.gpkg`.

### Gezamenlijke secundaire verbindingstoets

Secundaire waterlopen worden gegroepeerd als ze binnen 2 m van elkaar liggen.
Een groep is verbonden als een waterloop binnen 2 m van primair ligt.
Dat mag ook een waterloop van een andere beheerder zijn.

Dit bepaalt de indeling van de vectorlagen. Voor de inbranding worden
[waterlopen en duikers samen beoordeeld](#waterlopen-en-duikers).

## Duikers, sifons en hevels

- HYDAMO-duikers worden gelezen uit `duikersifonhevel`.
- RWS-duikers komen alleen uit de optionele duikerlaag in de Rijkswaterenbron.
- BGT- en OSM-duikers worden toegevoegd via de [TOML](#toml-configuratie).

Bij de koppeling aan primaire waterlopen is de koppelafstand standaard **0,5 m**
per uiteinde. Aanpassen kan met `--duiker-tolerance`.
Zie de [koppelregels](../reference/afwateringseenheden.md#duikervoorbereiding).

Met `--max-aansluitlengte 50` worden ook direct aansluitende stukken van maximaal
50 m uitgesloten als afwateringsdoel. Ze blijven wel ingebrand.
Zonder deze optie blijven aansluitstukken afwateringsdoelen.

Daarna worden [waterlopen en duikers samen beoordeeld](#waterlopen-en-duikers).
Dit bepaalt welke duikers worden ingebrand.

### Controle in QGIS

Open `controle.gpkg` naast `watersysteem.gpkg`.

| Controlelaag | Wat controleren? |
| --- | --- |
| `duikersifonhevel` | Koppeling aan primaire waterlopen; zie `reden`, `afstand_begin` en `afstand_eind`. |
| `duikers_waternet` | Behandeling op het raster; zie `behandeling` en `reden`. |

Een duiker zonder primaire koppeling kan wel bij een secundaire waterloop horen.
Gebruik `bronbestand`, `bronlaag` en `bron_fid` om het oorspronkelijke object terug te vinden.

Bij segmenten betekent `brandgeschikt` dat ze mogen worden ingebrand.
`doelgeschikt` betekent dat er een afwateringseenheid aan mag worden toegewezen.

### Afwateringseenheid aan een segment koppelen

Gebruik `segment_id` uit de afwateringseenheid om hetzelfde segment in
`hydroobject_segment` te vinden. `van_segment` en `naar_segment` in
`hydroobject_verbinding` gebruiken deze nummers ook.

De nummers gelden binnen dezelfde run. Broninformatie staat in
`hydroobject_segment`. Velden met `kunstwerk_` beschrijven een gekoppelde
stuw of gemaal en zijn anders leeg.

## Optionele brandlagen

Met lijnen en vlakken uit GeoPackages kunt u het reken-DEM verhogen of verlagen.
Deze lagen sturen de afstroming, maar voegen geen afwateringsdoelen toe.

| Instelling | Betekenis |
| --- | --- |
| `brandwaarde` | Hoogtewijziging in meters: negatief verlaagt, positief verhoogt. |
| `prioriteit` | Hoger getal heeft voorrang bij overlap tussen aanvullende lagen. |

- Een waarde bij het object gaat voor de TOML-instelling van de laag, daarna geldt `[defaults]`.
- Bij gelijke prioriteit wint de grootste wijziging. Verhoging en verlaging op dezelfde cel geven dan een fout.
- Wijzigingen worden niet opgeteld. Waarde `0` verandert de hoogte niet, maar kan wel een lagere prioriteit tegenhouden.
- Lijnen krijgen geen extra breedte. Gebruik daarvoor een vlak.
- Bij vlakken doen alle geraakte rastercellen mee. NoData buiten het DEM blijft NoData.

### Waterlopen en duikers

Waterlopen en duikers worden samen beoordeeld op het 2m-raster.
Ook diagonaal aangrenzende cellen tellen mee.
De verlagingen sturen de afstroming; het zijn geen werkelijke bodemhoogtes.

| Situatie | Verlaging |
| --- | ---: |
| Primaire waterloop buiten duikers | 200 m |
| Secundaire HYDAMO-waterloop met verbinding naar primair | 100 m |
| HYDAMO-duiker secundair-primair of secundair-secundair, met route naar primair | 100 m |
| Secundaire HYDAMO-waterloop zonder route naar primair; tertiaire HYDAMO-waterloop | Standaard 10 m |
| Aangesloten HYDAMO-duiker die niet onder de regels hierboven valt | Standaard 10 m |
| Duiker die alleen primair met primair verbindt | Geen |
| Duiker zonder twee aansluitingen | Geen; naar controle |

Voor de verlaging van 100 m tellen alleen verbindingen via primaire en secundaire
HYDAMO-waterlopen en geschikte HYDAMO-duikers. BGT, OSM en TOP10NL maken een
losliggend HYDAMO-stelsel niet alsnog diep.

- Duikerlijnen sluiten aan via hun uiteinden. Een secundair of tertiair eindpunt op de duiker telt ook mee.
- Bij duikervlakken worden aansluitingen langs de rand gezocht. Alleen kruisen is niet genoeg.
- Bij dubbele duikers gaat HYDAMO voor BGT, daarna OSM.
- Aanvullende lagen overschrijven de HYDAMO-inbranding niet.
- Duikers zijn geen afwateringsdoelen.

Met `geisoleerde_branddiepte_m` past u de ondiepe HYDAMO-verlaging aan.
De standaard is 10 m. Aanvullende bronnen gebruiken hun eigen `brandwaarde`.

Een rastercel heeft maar een stroomrichting. Kruisingen op verschillende
hoogtes blijven daardoor niet automatisch gescheiden.

### TOML-configuratie

[Download de voorbeeld-TOML](../reference/voorbeelden/brandlagen.toml).
Plaats deze naast `source_data` of pas de paden aan.

| Onderdeel | Invullen |
| --- | --- |
| `path`, `layer` | Bestand en laagnaam. Relatieve paden gelden vanaf de TOML. |
| `brandwaarde`, `prioriteit` | Waarden voor de laag; mogen ook per object zijn ingevuld. |
| `rol` | `water`, `duiker` of `overig` (bijvoorbeeld wegen). |
| `bron` | Bij duikers verplicht: `hydamo`, `bgt` of `osm`. |
| `[defaults]` | Standaardwaarden voor alle lagen. |

De bronnen moeten vooraf beschikbaar zijn:

- BGT en TOP10NL: bestaande GeoPackages.
- BGT-duikers: selectie van `bgt_kunstwerkdeel` met `plus-type = duiker`.
- OSM: het [downloadscript](../reference/bronlagen-downloaden.md#osm-kanalen) maakt vijf bestanden onder `source_data/osm/`.

Neem bij gebiedsselecties ook de tegelbuffers mee. De TOML downloadt niets.

In het voorbeeld geldt deze volgorde, met de hoogste prioriteit bovenaan:

| Aanvullende laag | Hoogtewijziging | Prioriteit |
| --- | ---: | ---: |
| BGT-water en BGT-duikers | -10 m | 2 |
| OSM-duikers | -10 m | 1 |
| OSM-kanalen, sloten, afvoerwatergangen en beken | -5 m | 1 |
| TOP10NL-waterdelen en waterlijnen | -5 m | 0 |

Duikers moeten wel voldoen aan de [aansluitregels](#waterlopen-en-duikers).
BGT-wegen staan uitgecommentarieerd: de proefwaarde is **+2 m**.
De waterlopen en duikers houden bij overlap met wegen hun behandeling.

```toml
--8<-- "docs/reference/voorbeelden/brandlagen.toml"
```

```console
pixi run --environment afwateringseenheden afwateringseenheden --bounds 184285 392054 185285 393054 --brandlagen-config brandlagen.toml --workers 32
```

### Brandlagen controleren in QGIS

| Bestand | Wat ziet u? |
| --- | --- |
| `brandlagen.gpkg` | Alle geselecteerde invoer, per bron in een aparte laag. |
| `berekening/tegels/<tegel>/brandbron.tif` | De gebruikte bron per rastercel. |

Niet elk object uit `brandlagen.gpkg` wordt ingebrand: overlap en duikerregels
bepalen wat wordt gebruikt. Bekijk daarvoor `brandbron.tif` en controleer
daarna de stroomrichtingen (LDD) en afwateringsvlakken.

Broncodes zijn labels, geen prioriteiten. `0` betekent geen inbranding.
De legenda staat bij `broncodes` in de rastermetadata.

## Uitvoer en hervatten

Elke run staat onder `processed_data/afwateringseenheden/<gebied>/<run-id>/`.

| Bestand | Inhoud |
| --- | --- |
| `afwateringseenheden.gpkg` | Het eindresultaat, met één laag: `afvoergebiedaanvoergebied`. |
| `brandlagen.gpkg` | Alle geselecteerde brandinvoer, met afzonderlijke lagen per bron. |
| `watersysteem.gpkg` | Vijf lagen: primaire, secundaire en niet-verbonden secundaire waterlopen, segmenten en verbindingen. |
| `controle.gpkg` | Niet-toegewezen gebieden, aanvullingen uit buurtegels, duikercontroles en bronobjecten zonder categorie. |
| `berekening/` | Tussenbestanden voor de berekening en het hervatten. |
| `productie.log` | Hoofdlog, inclusief de werkprocessen. |
| `run.json` | Instellingen, bronidentiteit, pakketversie en runstatus. |

Lever voor normaal gebruik `afwateringseenheden.gpkg` en `watersysteem.gpkg`.
Geef `controle.gpkg` apart mee voor beoordeling.
`brandlagen.gpkg` helpt bij het bekijken van de gebruikte invoer.

Onder `berekening/` staan:

- `ahn/`: verwijzingen naar de gebruikte AHN-tegels.
- `watersysteem/`: tussenlagen van de primaire waterlopen.
- `waterlopen_duikers/`: rasters met de gekozen behandeling van waterlopen en duikers.
- `tegels/`: resultaten per tegel en de tegelindeling in `tiles.gpkg`.
  `brandlagen_voorbereid.gpkg` bevat hier de aanvullende brandlagen voor het rekenen.

Gebruik voor het bekijken van de invoer **`brandlagen.gpkg` in de hoofdmap**.
Bewaar `berekening/` als u de run wilt hervatten.
De nieuwe indeling geldt voor nieuwe runs. Begin voor uitvoer met de oude
mapindeling een nieuwe run; bestaande bestanden worden niet verplaatst.

Niet-toegewezen gebieden staan in `controle.gpkg`, laag `niet_toegewezen`.
Controleer daar op ontbrekende bronnen, tegelranden en rekenproblemen.

```console
pixi run --locked afwateringseenheden --area alkmaar --run-id proef
pixi run --locked afwateringseenheden --area alkmaar --run-id proef --resume
```

Fouten in afzonderlijke tegels verhinderen het samenvoegen, terwijl overige
onafhankelijke tegels worden afgewerkt. Hervatten hergebruikt geldige resultaten.
Zie [productiemappen](configuratie.md#productiemappen) voor de compatibiliteitsvoorwaarden.

Gebruik na wijzigingen aan bronnen of instellingen een nieuwe run-ID.
`--resume` is alleen bedoeld voor dezelfde invoer en instellingen.
Bewerk invoer niet tijdens een berekening.

Gebruik voor eigen code de [Python-ingang](../reference/gebruik.md) of de
[lagere API](../reference/afwateringseenheden.md#dekking-en-hergebruik).
