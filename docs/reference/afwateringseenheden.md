---
editorial_status: ai
---

# Afwateringseenheden

De functionele uitleg staat bij [Afwateringseenheden](../bewerkte-lagen/afwateringseenheden.md).
Zie [Afwateringseenheden produceren](../produceren/afwateringseenheden.md) voor
de uitvoering, parallel rekenen en logbestanden.

## Bronselectie en afwateringsdoelen

`read_watersysteem_sources` leest waterlopen en kunstwerken.
Primaire waterlopen kunnen afwateringsdoelen zijn. Secundaire waterlopen sturen
de afstroming naar die doelen.

Zie [bronkeuze](../produceren/afwateringseenheden.md#doelmodi-en-bronnen)
en het [Python-voorbeeld](bewerkte-lagen-produceren.md#afwateringseenheden).

::: waterlagen.afwateringseenheden.read_watersysteem_sources

::: waterlagen.afwateringseenheden.WatersysteemSources

## Duikervoorbereiding

Duikers worden aan primaire waterlopen gekoppeld:

- Beide uiteinden moeten binnen de koppelafstand liggen: standaard **0,5 m** (`duiker_tolerance`).
- De waterlopen moeten een aansluitende route langs de duiker vormen. Alleen kruisen is niet genoeg.
- Van meerdere routes wordt de best passende gekozen.
- Onduidelijke koppelingen komen in `controle.gpkg`.

Daarna worden [waterlopen en duikers samen beoordeeld](../produceren/afwateringseenheden.md#waterlopen-en-duikers).
Dit bepaalt welke duikers worden ingebrand. Zie ook de
[controle-instructies](../produceren/afwateringseenheden.md#controle-in-qgis).

::: waterlagen.afwateringseenheden.read_duikersifonhevel

## Brandlagen

`read_brandlagen` leest de ingestelde lijnen en vlakken, met hun brandwaarde,
prioriteit en bron. Geef de configuratie mee met `brandlagen=config`.

Zie [brandwaarde, prioriteit en regels bij overlap](../produceren/afwateringseenheden.md#optionele-brandlagen)
en [uitvoer bekijken](../produceren/afwateringseenheden.md#brandlagen-controleren-in-qgis).

## Dekking en hergebruik

Met `overwrite=False` hergebruiken de Python-functies bestaande resultaten
als die nog geldig zijn.

Hervat een volledige berekening alleen met dezelfde bronnen en instellingen.
Begin na wijzigingen een nieuwe run. Wijzig geen bronbestanden terwijl
de berekening draait.

Met `landsgrens_path` geeft u het bestand met de landsgrens op. Deze grens
bepaalt waar ontbrekende AHN-hoogtes worden aangevuld. Bij een volledige
berekening wordt deze grens automatisch gebruikt.

Voor hergebruik van tegeluitvoer is ook `subcatchments.tif` nodig: dit bepaalt
de werkelijke buffer; CRS en resolutie moeten overeenkomen. Het opgegeven
samengevoegde eindbestand wordt na succes wel vervangen. Kies een nieuw eindpad
om de vorige versie te bewaren.

## Tegelresultaten

`gap_additions` bevat aanvullingen uit buurtegels en `remaining_gaps` de
resterende gaten. `boundary_issue_tile_ids` betreft randproblemen voordat het
resultaat is aangevuld. `calculation_duration_seconds` geeft de verwerkingstijd
per tegel, zonder wachttijd in de pool of het gezamenlijke samenvoegen.

`skipped_tile_ids` bevat tegels zonder segmentcellen op geldige DEM-hoogtes.
Hiervoor worden zowel het segmentraster als het NoData-masker en de eindige
hoogtewaarden van het DEM gecontroleerd. Voor overgeslagen tegels worden geen
LDD- of subcatchmentbestanden gemaakt; de voorbereide rasters blijven behouden.

`tiles.gpkg` wordt in de opgegeven `output_dir` geschreven. De laag `tiles`
bevat de geselecteerde kerntiles en een `tile_id`-kolom met de namen van de
bijbehorende tegelmappen.

De functie gebruikt standaard een worker. Parallelle berekeningen gebruiken
afzonderlijke `spawn`-processen en vereisen een script met een `__main__`-guard.

::: waterlagen.afwateringseenheden
