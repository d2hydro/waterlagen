---
editorial_status: ai
---

# Opslag van gegevens

## Beginnen zonder instellingen

Standaard staan downloads in `data/source_data/` en resultaten in `data/processed_data/` onder de projectmap. Opslagmappen mogen leeg zijn. Waterlagen maakt de benodigde mappen aan en haalt openbare brondata op zodra een run ze nodig heeft. Kies je zelf een GeoPackage, dan moet dat bestand op het ingestelde pad staan.

## Gegevens ergens anders bewaren

Open **Datastore kiezen** en kies een `.datastore`. Controleer de paden, wijzig zo nodig een bron en klik op **Runmaker openen**. Gebruik **Opslaan als…** voor een eigen bestand. Relatieve paden beginnen bij de map van het datastorebestand.

```text
DATA_DIR=./data
AHN_DATA_DIR=E:/Hoogtedata/AHN
AHN4_DATA_DIR=P:/Archief/AHN4/dtm_05
TOP10NL_FILE=P:/Basisdata/mijn_top10nl.gpkg
```

Onder **Basisbronnen** kies je per bron de opslagmap. Klap **AHN** open voor de tegelmappen van AHN6, AHN5 en AHN4. Klap **BAG**, **BGT**, **BRP** of **TOP10NL** open om een eigen GeoPackage te kiezen. **Resultatenmap kiezen…** bij de runnaam geldt voor één run.

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
