---
editorial_status: ai
---

# DEM produceren

<span id="starten"></span>

Kies **DEM (hoogte)** in de [Run Maker](index.md). Het gebied selecteert volledige tegels. Het hoogtemodel kan hierdoor buiten de gekozen grens doorlopen.

## Landgebruik vinden of produceren

DEM gebruikt het landgebruik voor de tegelindeling en de ligging van gebouwen. Kies bij **DEM → Laagopties**:

- **Automatisch:** laat **Landgebruikrun (optioneel)** leeg. DEM zoekt eerst in het gekozen gebied naar een geschikte afgeronde run. Vindt DEM geen geschikte run, dan wordt landgebruik eerst berekend.
- **Eigen run:** kies met het mapicoon een afgeronde run die alle tegels en de zoekruimte rond gebouwen dekt.

## Hoogtebron

Standaard wordt AHN gebruikt. Voor eigen maaiveldhoogtes opent u bij **DEM → Laagopties** de rij **Eigen DTM (.vrt)** en kiest u uw VRT-bestand.

Gebruik één rasterband met hoogtes in meters ten opzichte van NAP. Het raster moet hetzelfde coördinatenstelsel, dezelfde celgrootte en dezelfde celuitlijning hebben als het landgebruik. Zorg voor dekking van de volledige tegels én de zoekruimte eromheen.

## Integer- en floatuitvoer

Open `dem_float.tif` voor hoogtes direct in meters. `dem.tif` bevat dezelfde hoogtes als gehele getallen met een schaalfactor. Beide staan in `data/processed_data/dem/<gebied>/<run-id>/`. [Eenheden en hoogte ten opzichte van NAP](../bewerkte-lagen/dem.md#uitvoer)

## Controleren en hervatten

- Bekijk `dem_bron.tif` om te zien of een hoogte uit het terreinmodel, interpolatie of een gebouwschatting komt.
- Bekijk `nodata.gpkg` voor ontbrekende terrein- en gebouwhoogtes. In `dem_coverage.json` staat hoeveel cellen in het **eindraster** leeg zijn. Een afgeronde productie kan gaten bevatten.
- Hervat met dezelfde runnaam, invoer en rekeninstellingen. Het aantal workers mag wijzigen.
- Bij hervatten of overschrijven blijft de eerder gekoppelde landgebruikrun in gebruik. Kies een nieuwe DEM-runnaam om van landgebruikrun te wisselen.

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
    | `--interpolation-max-distance-m` | 250 | Zoekafstand voor interpolatie; 0 schakelt vullen uit |

[Opslag en aantal workers instellen](configuratie.md#workers-voor-landgebruik-en-dem){ .md-button }
