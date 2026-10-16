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

[Download het PowerShell-voorbeeld](voorbeelden/afwateringseenheden_issue63.ps1).
Het selecteert 1 × 1 km rond RD-punt `(184785, 392554)` uit issue 63.
Gebruik hiervoor `settings.crs = EPSG:28992`. Zie de
[gedeelde gebiedsuitleg](cli.md#eigen-rechthoekig-gebied).

1. Maak de brandlagen in QGIS en sla ze op in een GeoPackage.
2. Wijs de bestanden en lagen aan in de [brandlagen-TOML](#toml-configuratie).
3. Start vanuit de repositoryroot:

   ```powershell
   .\docs\produceren\voorbeelden\afwateringseenheden_issue63.ps1 -BrandlagenConfig '.\invoer\brandlagen.toml'
   ```

4. Open de gelogde resultaatmap en laad de uitvoer in QGIS.
5. Pas zo nodig de brandlagen aan, sla ze op en start opnieuw.

De vier grenzen en het configuratiepad zijn parameters bovenaan het script.
Een relatief configuratiepad geldt vanaf de werkdirectory waarin u het script
start. GeoPackage-paden in de TOML blijven relatief aan het TOML-bestand.
Het script voert de productie vanuit de repositoryroot uit en geeft fouten door.

Iedere uitvoering krijgt een nieuwe UTC-runmap. Na wijzigingen aan brandlagen
is een nieuwe run nodig, ook bij `--overwrite`. Gebruik `--resume` alleen voor
een onderbroken run met dezelfde invoer. Bewerk invoer niet tijdens een run.
Ook zonder optionele brandlagen blijft de vaste HYDAMO-inbranding actief.

### Verwerking

1. Het gebied selecteert volledige tegelkernen van 10 x 10 km.
2. De productie haalt de benodigde AHN-tegels, bestuurlijke gebieden en HYDAMO
   op, of hergebruikt lokale bronnen. De AHN-selectie dekt ook de tegelbuffers.
3. HYDAMO-objecten worden ruimtelijk geselecteerd met de benodigde context.
   De beheerder van een object vormt geen extra filter.
4. De productie berekent de tegels en voegt de bruikbare resultaten samen.
   De gebiedsgrens knipt het resultaat niet af.

De tegelbuffer is 2000 m, de rasterresolutie 2 m, de inbranddiepte voor
secundaire waterlopen 100 m en de maximale opvuldiepte 50 m. De vaste seed is
12345. De landsgrens begrenst de AHN-interpolatie tot Nederland. Dit staat los
van de gekozen gebiedsgrens als invoerselectie.
De betekenis en beperkingen staan bij
[Afwateringseenheden](../bewerkte-lagen/afwateringseenheden.md).

## Optionele brandlagen

U kunt eigen GeoPackage-lagen met lijnen en polygonen gebruiken om het reken-DEM
te verhogen of te verlagen. Bereid de geometrie en attributen in QGIS voor.
Er worden geen bronnen voor deze lagen gedownload of watergangen automatisch
uit afgeleid. De lagen voegen geen afwateringsdoelen toe.

| QGIS-kolom | Waarde |
| --- | --- |
| `brandwaarde` | Relatieve wijziging in meters: negatief verlaagt, positief verhoogt. |
| `prioriteit` | Geheel getal; hoger heeft voorrang binnen de optionele lagen. |

De ingevulde objectwaarde gaat voor de laagdefault, die voor de globale default
gaat. Ontbrekende kolommen en `NULL` gebruiken de defaults. Zonder beschikbare
waarde volgt een fout. Het getal **0** is een expliciete waarde: geen
hoogtewijziging, maar bij hogere prioriteit wel blokkering van een lagere
optionele bewerking. Ongeldige ingevulde waarden worden niet door defaults vervangen.

De vaste rangorde is **primair > secundair > optioneel**, ongeacht de optionele
prioriteitsgetallen. Bij gelijke optionele prioriteit wint de grootste absolute
brandwaarde. Positief en negatief bij dezelfde prioriteit op dezelfde rastercel
is een fout, ook als een hogere prioriteit of vaste waterloop die cel overstemt.
Brandwaarden worden niet opgeteld. De gekozen wijziging wordt eenmaal toegepast.

Lijnen krijgen geen automatische breedtebuffer. Lever voor een fysieke breedte
een polygoon aan. Polygonen branden alle geraakte cellen in (`all_touched=True`);
lijnen gebruiken de bestaande lijnrasterisatie. Ook geometrieën die elkaar niet kruisen kunnen in één cel
terechtkomen. Branden verandert geen NoData buiten de geldige DEM-dekking.

### TOML-configuratie

[Download het configuratievoorbeeld](../reference/voorbeelden/brandlagen.toml).
Het voorbeeld gebruikt bestaande BGT- en TOP10NL-GeoPackages. Plaats de TOML
naast `source_data` of pas de paden aan. Eigen correcties kunt u toevoegen.

De duikerlagen in het voorbeeld zijn vooraf geselecteerd voor de voorbeeldtegel
inclusief buffer. BGT bevat alleen `bgt_kunstwerkdeel` met `plus-type = duiker`;
OSM bevat lijnen met `tunnel=culvert`. Maak voor een ander gebied nieuwe selecties.
De TOML haalt deze gegevens niet zelf op.

| Laag | Brandwaarde | Voorrang |
| --- | ---: | --- |
| HYDAMO primair | −200 m | Vast, hoogste |
| HYDAMO secundair | −100 m | Vast, daarna |
| Eigen waterloopcorrecties (optioneel) | −40 m | Prioriteit 3 |
| `bgt_waterdeel` | −40 m | Prioriteit 2 |
| BGT-duikers (`bgt_duiker`) | −40 m | Prioriteit 2 |
| `top10nl_waterdeel_vlak` en `top10nl_waterdeel_lijn` | −40 m | Prioriteit 1 |
| OSM-duikers (`osm_culvert`) | −40 m | Prioriteit 0, laagste |

De verlaging stuurt de LDD en stelt geen echte waterbodemhoogte voor.
De voorbeeldwaarde −40 m is een proefinstelling; controleer aansluitingen en
afwatering. TOP10NL-lijnen worden zonder breedtebuffer ingebrand.
TOP10NL vult cellen aan waar BGT ontbreekt. Verlagingen worden niet opgeteld.
De TOML-volgorde bepaalt geen voorrang. Attributen op objecten blijven voorgaan
op de defaults. Alle objecten uit de gekozen lagen binnen het rekengebied doen
mee, zonder filter op status, type water of hoogteligging.

```toml
--8<-- "docs/reference/voorbeelden/brandlagen.toml"
```

`[defaults]` is optioneel en bevat globale defaults. Elke `[[lagen]]` heeft
verplicht `path` en `layer`, met optioneel `brandwaarde` en `prioriteit` als
laagdefaults. Relatieve paden worden ten opzichte van het TOML-bestand opgelost,
niet ten opzichte van de werkdirectory. Kolomnamen in QGIS staan vast;
onbekende configuratiesleutels worden afgewezen. Defaults zijn niet verplicht
als alle geselecteerde objecten zelf geldige waarden hebben.

```console
pixi run --locked afwateringseenheden --area alkmaar --brandlagen-config brandlagen.toml
```

De gewone productie controleert brandinvoer vóór de AHN-voorbereiding. Invoer-
en tekenconflicten worden gezamenlijk gemeld met bestand, laag en FID. De
conflictcontrole geldt op de gekozen rekenrasters, inclusief tegelbuffers,
onafhankelijk van de AHN-dekking. De controletijd hangt af van het aantal
geometrieën en hun overlap.

Een gevalideerde selectie wordt lokaal opgeslagen; workers lezen daaruit hun
eigen rekengebied. Bij ongewijzigde bronnen en instellingen wordt ook deze
voorbereiding hergebruikt. Bewerk bronbestanden niet tijdens een berekening.

### Brandlagen controleren in QGIS

| Uitvoer binnen de runmap | Inhoud |
| --- | --- |
| `tiles/brandlagen.gpkg`, laag `brandlagen` | Gebruikte optionele objecten, inclusief buffergebied. Met effectieve `brandwaarde`, `prioriteit`, `broncode`, bronbestand, bronlaag en oorspronkelijke FID. |
| `tiles/<tegel>/brandbron.tif` | Winnende bron per cel, op hetzelfde rooster als het reken-DEM inclusief buffer. |

Broncode **1** is primair HYDAMO, **2** secundair HYDAMO. Vanaf **3** volgt
iedere opgegeven TOML-laag een eigen code, in configuratievolgorde. Deze codes
zijn labels, geen prioriteiten. De bronverwijzingen staan ook in de GeoTIFF-metadata
onder `broncodes`. **0** betekent geen inbranding; NoData ligt buiten de geldige
DEM-dekking. Een winnend object met brandwaarde 0 houdt zijn eigen broncode.

Open het bronraster en de brandobjecten in QGIS om overlap en aansluitingen te
controleren. Controleer daarna de LDD en afwateringsvlakken. Aanvullende
brandlagen maken geen nieuwe waterloopsegmenten of afwateringsdoelen.

Voor Python gebruikt u `Brandlaag`, `BrandlagenConfig`, `read_brandlagen_config`
en `read_brandlagen`; zie het
[uitvoerbare voorbeeld](../reference/bewerkte-lagen-produceren.md#afwateringseenheden).
Dat voorbeeld toont de losse bouwstenen; de normale productie-ingang voert
de volledige controle al vóór de zware bronvoorbereiding uit.

## Uitvoer en hervatten

Elke run staat onder `processed_data/afwateringseenheden/<gebied>/<run-id>/`.

| Bestand | Inhoud |
| --- | --- |
| `afwateringseenheden.gpkg` | Samengestelde afwateringseenheden. |
| `watersysteem.gpkg` | Voorbereid watersysteem voor alle geselecteerde tegels. |
| `input/ahn.vrt` | Gebiedsspecifieke verwijzingen naar gedeelde AHN-tegels. |
| `tiles/tiles.gpkg` | Geselecteerde tegelkernen. |
| `tiles/brandlagen.gpkg` en `tiles/brandlagen.json` | Gevalideerde optionele brandobjecten en bron-/grididentiteit, indien gebruikt. |
| `tiles/<tegel-id>/` | Rasters, polygonen en status per rekentegel. |
| `productie.log` | Hoofdlog, inclusief de werkprocessen. |
| `run.json` | Instellingen, bronidentiteit, pakketversie en runstatus. |

```console
pixi run --locked afwateringseenheden --area alkmaar --run-id proef
pixi run --locked afwateringseenheden --area alkmaar --run-id proef --resume
```

Fouten in afzonderlijke tegels verhinderen het samenvoegen, terwijl overige
onafhankelijke tegels worden afgewerkt. Hervatten hergebruikt geldige resultaten.
Zie [productiemappen](configuratie.md#productiemappen) voor de compatibiliteitsvoorwaarden.

De brandconfiguratie en bronidentiteiten worden vastgelegd in `run.json`.
Gewijzigde bronnen of instellingen vereisen bij de productie een nieuwe run-ID.
Lagere Python-functies vernieuwen raster- en tegeluitvoer met gewijzigde
brandinvoer ook bij `overwrite=False`. Oude uitvoer zonder brandmetadata wordt
eenmalig opnieuw berekend; zie het
[API-hergebruikcontract](../reference/afwateringseenheden.md#dekking-en-hergebruik).

Gebruik voor eigen code de [Python-ingang](../reference/gebruik.md) of de
[lagere API](../reference/afwateringseenheden.md#dekking-en-hergebruik).
