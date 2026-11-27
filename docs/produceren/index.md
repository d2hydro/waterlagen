---
editorial_status: ai
---

# Zelf produceren

[Installeer het productiepakket](installatie.md){ .md-button .md-button--primary }

## Een productie starten

1. Dubbelklik op **run-maken.bat**. Controleer de getoonde **datastore** of klik op **Datastore openen…**. Klik op **Runmaker openen**.
2. Kies het gebied en vink de gewenste kaartlagen aan.
3. Vul de **Runnaam** in. Kies zo nodig een andere uitvoermap met **Resultatenmap kiezen…**.
4. Klik op **Opslaan en starten**. Kies **Alleen opslaan** om het `.bat`-bestand later te starten.

Vanuit de terminal: voer `pixi run --locked run-maken` uit in de projectmap en laat de terminal open.

## Bronnen en resultaten

| Map | Inhoud |
| --- | --- |
| `source_data/` | Gedownloade bronbestanden voor hergebruik. |
| `processed_data/<laag>/<gebied>/<runnaam>/` | Resultaten van de run. Bij een eigen resultatenmap komt `<laag>/<gebied>/<runnaam>/` onder die map. |

Bekijk de uitvoer per laag: [Afwateringseenheden](afwateringseenheden.md), [Functioneel landgebruik](landgebruik.md), [Hoogtemodel (DEM)](dem.md) en [Inwoners en personenauto’s](inwoners-personenautos.md).

## Hulp en naslag

[Opslag instellen](configuratie.md) · [Terminal en Linux](cli.md) · [Installatiehulp](installatie.md#als-een-opdracht-niet-werkt) · [Probleem melden](https://github.com/d2hydro/waterlagen/issues)
