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

Standaard wordt per cel de nieuwste beschikbare AHN-maaiveldhoogte op 0,5 m gekozen in de volgorde AHN6, AHN5, AHN4. De selectie vindt vóór interpolatie en gebouwbewerking plaats. Met `--ahn-version latest` kiest u expliciet de nieuwste hoogte per cel. Met `--ahn-version 4`, `5` of `6` kunt u één versie vastzetten. In `ahn_versie.tif` staan de gebruikte generaties (4, 5 of 6) vóór interpolatie. Cellen zonder geldige oorspronkelijke AHN-hoogte hebben code 0 (NoData). Kies in de Runmaker bij **DEM → Laagopties → Hoogtebron** voor **Nieuwste beschikbare AHN**, één AHN-versie of **Eigen DTM (.vrt)**. Een vaste versie vereist alle benodigde tegels binnen de gekozen grens. Een tegel mag lege cellen bevatten. De Runmaker controleert AHN4 en AHN5 lokaal. Voor AHN6 wordt de lijst na 24 uur bijgewerkt. Tijdens het wachten of downloaden toont de Runmaker de voortgang. Met **Nu verversen** controleert u direct opnieuw.

Gedownloade GeoTIFF-tegels blijven in `source_data/ahn/` van de datastore. AHN4 staat in `dtm_05/`, AHN5 in `ahn5/dtm_05/` en AHN6 in `ahn6/dtm_05/`. Volgende runs gebruiken dezelfde bestanden.

Bekijk na afloop **AHN-resultaat bekijken** in de Runmaker of open `ahn_overzicht.html` in de resultatenmap voor de verdeling binnen het gebied. Open na een run met **Nieuwste beschikbare AHN** de laag `ahn_versie.tif` naast het DEM. Klik op een rastercel voor de gebruikte generatie. De laag `dem_bron.tif` laat zien waar de eindhoogte uit het maaiveld, een gebouwbewerking of interpolatie komt.

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
