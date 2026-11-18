---
editorial_status: ai
---

# Opslag van gegevens

## Beginnen zonder instellingen

Standaard staan downloads in `data/source_data/` en resultaten in `data/processed_data/` onder de projectmap.

## Gegevens ergens anders bewaren

Open `.datastore` naast `pixi.toml` in een teksteditor. Vervang `./data` door uw eigen map, bijvoorbeeld:

```text
DATA_DIR=D:/waterdata
```

Sla op als UTF-8 zonder BOM en start de volgende productie. Om bestaande gegevens te blijven gebruiken, moet u ze zelf naar de nieuwe locatie verplaatsen. Met `SOURCE_DATA_DIR` en `PROCESSED_DATA_DIR` kunt u bron en uitvoer apart instellen. Gelijknamige omgevingsvariabelen hebben voorrang.

## Productiemappen

Elke productie heeft een eigen map: `processed_data/<product>/<gebied>/<run-id>/`. Bekijk `run.json` voor de status en instellingen en `productie.log` voor het verloop. Gebruik een nieuwe runnaam bij gewijzigde invoer, softwareversie of rekeninstellingen. Bewaar de tussenbestanden om te kunnen hervatten.

## Openbare brandbronnen

BGT en OSM worden per gebied bewaard; TOP10NL wordt landelijk gedeeld. Het productielog vermeldt het gebruikte pad. Houd de bronbestanden en hun JSON bij elkaar, ook voor hervatten. [Brandlagen kiezen](afwateringseenheden.md#test-met-eigen-gebied-en-brandlagen)

## Workers voor landgebruik en DEM

`FUNCTIONEEL_LANDGEBRUIK_WORKERS` is standaard 4; `DEM_WORKERS` is standaard 1.
Beide zijn positieve gehele getallen, instelbaar via `.env` of de omgeving.
`--workers` heeft voorrang voor de aangeroepen workflow. Automatische
landgebruikproductie vanuit DEM gebruikt de eigen landgebruikinstelling.
Workers mogen bij hervatten veranderen zonder de uitvoer opnieuw te maken.
