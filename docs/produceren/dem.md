---
editorial_status: ai
---

# DEM produceren

<span id="starten"></span>

Kies **DEM (hoogte)** in de [Run Maker](index.md). Het gebied selecteert volledige tegels. Het hoogtemodel kan hierdoor buiten de gekozen grens doorlopen.

## Landgebruik vinden of produceren

Laat **Landgebruik als basis** op **Automatisch** staan. Een geschikte afgeronde landgebruikrun wordt hergebruikt. Ontbreekt die, dan wordt landgebruik eerst berekend. Wilt u een specifieke run gebruiken? Kies **Zelf kiezen** en vervolgens **Landgebruikrun kiezen**. Een zelfgekozen run moet alle benodigde tegels en voldoende ruimte rond de gebouwen bevatten.

Een eigen AHN-mozaïek (`.vrt`) moet ook de zoekomgeving rond het gebied dekken.

## Integer- en floatuitvoer

Open `dem_float.tif` voor hoogtes direct in meters. `dem.tif` bevat dezelfde hoogtes als gehele getallen met een schaalfactor. Beide staan in `data/processed_data/dem/<gebied>/<run-id>/`. [Eenheden en hoogte ten opzichte van NAP](../bewerkte-lagen/dem.md#uitvoer)

## Controleren en hervatten

- Bekijk `dem_bron.tif` om te zien of een hoogte uit AHN, interpolatie of een gebouwschatting komt.
- Bekijk `nodata.gpkg` voor ontbrekende terrein- en gebouwhoogtes. In `dem_coverage.json` staat hoeveel cellen in het **eindraster** leeg zijn. Een afgeronde productie kan gaten bevatten.
- Hervat met dezelfde runnaam, invoer en rekeninstellingen. De eerder gekozen landgebruikrun blijft gekoppeld. Het aantal workers mag wijzigen.

<span id="tijdelijk-vergrendelde-uitvoerbestanden"></span>

[Hulp bij vergrendelde uitvoer](landgebruik.md#tijdelijk-vergrendelde-uitvoerbestanden)

## Instellingen en workers

??? info "Standaardwaarden voor gebouwhoogtes, zoekafstanden en workers"

    | Optie | Standaard | Betekenis |
    | --- | --- | --- |
    | `--area` | `nederland` | Nederland, Alkmaar, Alkmaar-centrum of waterschapscode |
    | `--workers` | `DEM_WORKERS`, anders 1 | Gelijktijdige DEM-tegels |
    | `--building-workers` | `DEM_BUILDING_WORKERS`, anders 4 | Gelijktijdige batches voor gebouwhoogten |
    | `--building-initial-buffer-m` | 1 | Eerste gebouwzoekafstand |
    | `--building-buffer-step-m` | 1 | Toename zonder geldige donor |
    | `--building-percentile` | 75 | Percentiel bij eerste geslaagde zoekactie |
    | `--building-offset-m` | 0.05 | Toeslag op de geschatte vloerpeil t.o.v. lokaal maaiveld in meters; 0 schakelt de toeslag uit |
    | `--building-max-search-distance-m` | 5 | Maximale gebouwzoekafstand |
    | `--interpolation-max-distance-m` | 250 | AHN-interpolatieafstand; 0 schakelt vullen uit |

[Opslag en aantal workers instellen](configuratie.md#workers-voor-landgebruik-en-dem){ .md-button }
