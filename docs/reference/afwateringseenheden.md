---
editorial_status: ai
---

# Afwateringseenheden: Python-API

Deze pagina beschrijft de Python-functies voor het voorbereiden van het
watersysteem en het berekenen van afwateringseenheden. Zie de
[functionele handleiding](../bewerkte-lagen/afwateringseenheden.md) voor de
berekeningswijze en de [productiehandleiding](../produceren/afwateringseenheden.md)
voor uitvoering met Pixi.

## Gebruik vanuit Python

`waterlagen.afwateringseenheden.productie.main` voert dezelfde workflow uit als
het productiecommando: bronvoorbereiding, watersysteem, rasterverbindingen en
tegelberekening, met runbeheer. Deze ingang haalt ontbrekende standaardbronnen
en expliciet ingestelde openbare brandbronnen op, behalve bij offline gebruik.
Zie de [productie-API](productie.md#afwateringseenheden) voor de parameters.

Met de losse functies stelt u zelf de workflow samen. Voor
`calculate_afwateringseenheden_tiles` moeten het AHN-VRT, het voorbereide
watersysteem en eventuele brandbestanden al beschikbaar zijn, met dekking van
alle kerntegels inclusief buffers. De tegelberekening downloadt deze bronnen
niet. Het [volledige Python-voorbeeld](bewerkte-lagen-produceren.md#afwateringseenheden)
toont downloads en voorbereiding met de bestaande bouwstenen.

`calculate_afwateringseenheden_tiles` knipt het samengevoegde resultaat standaard
op `gebied` (`clip_to_area=True`). De productie gebruikt `False` en behoudt de
volledige kerntegels. Het voorbeeld kiest bewust een eigen tegelgrootte en oorsprong;
het is geen automatisch beheerde productierun.

## Bronselectie en afwateringsdoelen

`read_watersysteem_sources` leest lokale HYDAMO- en Rijkswaterenbestanden en
geeft een `WatersysteemSources` terug. Gebruik `targets` en `points` voor
`prepare_watersysteem`; behoud `primary`, `secondary`, `tertiary` en `culverts`
voor de omringende rekencontext. `write_watersysteem` schrijft het voorbereide
watersysteem. Deze functies downloaden geen bronnen.

Zie de functionele uitleg over [bronnen](../bewerkte-lagen/afwateringseenheden.md#bronlagen)
en [afwateringsdoelen](../bewerkte-lagen/afwateringseenheden.md#afwateringsdoelen).

## Duikervoorbereiding

`read_duikersifonhevel` leest duikers uit een lokaal GeoPackage.
`prepare_watersysteem` zoekt hun geometrische koppeling aan primaire waterlopen:

- Beide uiteinden moeten binnen de koppelafstand liggen: standaard **0,5 m** (`duiker_tolerance`).
- De waterlopen moeten een aansluitende route langs de duiker vormen. Alleen kruisen is niet genoeg.
- Van meerdere routes wordt de best passende gekozen.
- Onduidelijke koppelingen komen in `controle.gpkg`.

Dit is een andere stap dan `prepare_waternet`: die beoordeelt aansluitingen
tussen waterlopen en duikers op de rekenrasters en bereidt hun inbranding voor.
Een bruikbare duiker hoeft dus niet aan beide uiteinden op een primaire waterloop
aan te sluiten. Voer deze stap vóór de tegelberekening uit, ook zonder optionele
brandlagen, om de gezamenlijke beoordeling uit de productie te gebruiken.
Zie [inbranding](../bewerkte-lagen/afwateringseenheden.md#waterlopen-en-duikers-inbranden)
en [controle in QGIS](../produceren/afwateringseenheden.md#controle-in-qgis).

::: waterlagen.afwateringseenheden.waternet.prepare_waternet
    options:
      show_root_heading: true
      show_root_full_path: false
      heading_level: 3
      separate_signature: true

## Brandlagen

`read_brandlagen_config` leest een TOML-bestand naar een `BrandlagenConfig`;
relatieve paden worden vanaf de TOML bepaald. Dit leest of downloadt nog geen
brongegevens. Geef het object met `brandlagen=config` aan
`waterlagen.afwateringseenheden.productie.main` voor de volledige workflow.

`Brandlaag.openbare_bron` kiest automatische voorbereiding van een ondersteunde
BGT-, TOP10NL- of OSM-laag. De productie-ingang roept hiervoor
`prepare_brand_sources` aan. In een eigen workflow doet u dat zelf, met de
volledige rekenomgeving inclusief buffers. Gebruik daarna de teruggegeven
`.config`: `read_brandlagen(config)` leest de lokale objecten voor
`prepare_waternet`, en `calculate_afwateringseenheden_tiles` krijgt dezelfde
configuratie via `brandlagen=config`. Zonder `openbare_bron` moet de gebruiker
het bestand vooraf aanleveren. Het Python-voorbeeld toont deze volgorde.

::: waterlagen.afwateringseenheden.brand_sources.prepare_brand_sources
    options:
      show_root_heading: true
      show_root_full_path: false
      heading_level: 3
      separate_signature: true

Zie [TOML-instellingen](../produceren/afwateringseenheden.md#toml-configuratie),
[inbranding en overlapregels](../bewerkte-lagen/afwateringseenheden.md#optionele-brandlagen)
en [uitvoer bekijken](../produceren/afwateringseenheden.md#brandlagen-controleren-in-qgis).

## Dekking en hergebruik

Met `overwrite=False` hergebruiken de Python-functies bestaande resultaten
als die nog geldig zijn.

Hervat een volledige berekening alleen met dezelfde bronnen en instellingen.
Begin na wijzigingen een nieuwe run. Wijzig geen bronbestanden terwijl
de berekening draait.

Met `landsgrens_path` geeft u het bestand met de landsgrens op. Deze grens
bepaalt waar ontbrekende AHN-hoogtes worden aangevuld. De productie-ingang
bereidt deze bron automatisch voor en geeft het pad mee.

Voor hergebruik van tegeluitvoer is ook `subcatchments.tif` nodig. De vier
afstanden tussen de rasterbegrenzing en de kerntegel moeten gelijk en
niet-negatief zijn, binnen de numerieke tolerantie. Die afstand is de beschikbare
rekenbuffer; ook CRS en resolutie moeten passen. Bij hergebruik geldt deze
buffer uit het bestand, niet een nieuw opgegeven `tile_buffer_m`. Kies daarom
een nieuwe uitvoermap om met een andere buffer te rekenen.

Het opgegeven samengevoegde eindbestand wordt na succes wel vervangen.
Kies een nieuw eindpad om de vorige versie te bewaren. Voor beheerde runs gelden
de [runcompatibiliteitsvoorwaarden](../produceren/configuratie.md#productiemappen).

## Tegelresultaten

`calculate_afwateringseenheden_tiles` gebruikt standaard kerntegels van
10 × 10 km met een buffer van 2 km rondom, net als de productiecommando's.
Python-aanroepen zonder `tile_size_m` gebruiken voortaan 10 km in plaats van
5 km. Bestaande productiecommando's veranderen hierdoor niet. Geef
`tile_size_m` expliciet op voor een andere tegelgrootte en kies bij een
gewijzigd rooster een nieuwe uitvoermap. Het Python-voorbeeld kiest bewust
kleinere tegels met `TILE_SIZE_M`.

`gap_additions` bevat aanvullingen uit buurtegels en `remaining_gaps` de
resterende gaten. `boundary_issue_tile_ids` betreft randproblemen voordat het
resultaat is aangevuld. `calculation_duration_seconds` geeft de verwerkingstijd
per tegel, zonder wachttijd in de pool of het gezamenlijke samenvoegen.

`skipped_tile_ids` bevat tegels zonder segmentcellen op geldige DEM-hoogtes.
Hiervoor worden zowel het segmentraster als het NoData-masker en de eindige
hoogtewaarden van het DEM gecontroleerd. Voor overgeslagen tegels worden geen
LDD- of subcatchmentbestanden gemaakt; de voorbereide rasters blijven behouden.

`tiles.gpkg` wordt in de opgegeven `output_dir` geschreven. De laag `tiles`
bevat de geselecteerde kerntegels en een `tile_id`-kolom met de namen van de
bijbehorende tegelmappen.

`calculate_afwateringseenheden_tiles` gebruikt standaard één worker. Parallelle berekeningen gebruiken
afzonderlijke `spawn`-processen en vereisen een script met een `__main__`-guard.

### Randfilter en aanvulling

Bij een positieve buffer toetst het randfilter de vlakken aan de omtrek van
de kerntegel, uitgebreid met `max(tile_buffer_m - resolution_m, 0)` meter.
Deze toetslijn ligt één rastercel binnen de buitenrand van het rekengebied.
Vlakken die de lijn raken worden uitgesloten, zowel uit het kernresultaat als
uit mogelijke aanvullingen voor buurtegels. Bij buffer `0` is dit filter uitgeschakeld.

Per gat worden de bruikbare vlakken van elke buurtegel op dat gat geknipt.
De keuzevolgorde tussen buurtegels is:

1. Grootste gezamenlijke oppervlakte die het gat bedekt.
2. Bij gelijke oppervlakte: grootste afstand van die bedekking tot de buitenrand
   van het rekengebied van de buurtegel, inclusief buffer.
3. Bij gelijke afstand: oplopend `tile_id`.

Elke volgende buurtegel vult alleen het dan nog ontbrekende deel aan.
`bron_tegel` en `keuzevolgorde` in `gap_additions` leggen de herkomst vast.
De [functionele uitleg](../bewerkte-lagen/afwateringseenheden.md#tegels-buffers-en-samenvoegen)
beschrijft wat deze aanvulling voor het resultaat betekent.

### Rekenbuffer instellen

`calculate_afwateringseenheden_tiles` accepteert `tile_buffer_m` (standaard
2000 m). In het [Python-voorbeeld](bewerkte-lagen-produceren.md#afwateringseenheden)
stelt u dit in met `TILE_BUFFER_M` en kiest u een nieuwe `EXPERIMENT`-naam.
De nieuwe uitvoermap voorkomt hergebruik van tegelrasters met de oorspronkelijke
buffer. Zorg dat de bronnen ook het grotere rekengebied dekken.

De productieopdracht gebruikt een vaste buffer van 2 km en heeft hiervoor geen
CLI-optie. Een andere buffer vraagt een eigen Python-workflow; de berekening
vergroot de buffer niet automatisch bij randproblemen.

## Functies en resultaattypen

::: waterlagen.afwateringseenheden
    options:
      heading_level: 3
      separate_signature: true
