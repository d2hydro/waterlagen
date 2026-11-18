---
editorial_status: ai
---

# Functioneel landgebruik produceren


Kies **Functioneel landgebruik** in de [Run Maker](index.md). Ook voor een klein gebied kunnen landelijke bronbestanden nodig zijn. Zorg dat de BAG-bronmap schrijfbaar is voor de pandindex.

<span id="vooraf"></span>
<span id="starten"></span>

??? info "Een eigen BGT-bestand of gebouwcontext gebruiken?"

    Een eigen BGT-GeoPackage moet de voorbereide wegdelen, ondersteunende wegdelen, begroeide en onbegroeide terreindelen en waterdelen met einddatumvelden bevatten. [BGT-vlakken voorbereiden](bgt-vlakken.md)

    Gebruikt u de kaart als basis voor een DEM? Houd de gebouwcontext rond de tegels minstens zo groot als de maximale zoekafstand voor gebouwhoogtes. Beide zijn standaard 5 m.

## Resultaten

Open `functioneel_landgebruik.tif` in QGIS. U vindt het raster in `data/processed_data/functioneel_landgebruik/<gebied>/<run-id>/`. Laad `functioneel_landgebruik.qml` als de legenda ontbreekt. Bewaar de `.tif`, `.tif.aux.xml` en `.qml` bij elkaar.

<span id="gaten-aanvullen-en-bronnenraster"></span>

## NoData controleren

- **Welke bron leverde deze cel?** Bekijk `functioneel_landgebruik_bronnen.tif` met de bijbehorende JSON-legenda.
- **Waarom ontbreekt hier een klasse?** Open `nodata.gpkg` en lees `bron` en `reden`. De controle toont resterende gaten binnen het landgebied.
- **Hoe is een klasse bepaald?** Zie [indeling, bronvolgorde en beperkingen](../bewerkte-lagen/functioneel-landgebruik.md).

<span id="bag-controleren-brongegevens-en-statusselectie"></span>
<span id="stap-6-controleren"></span>
<span id="meerdere-gemalen-in-een-pand-controleren"></span>
<span id="de-codetabel-aanpassen"></span>
<span id="bewerken-in-excel"></span>

## Eigen codes of een pand controleren

[Eigen codetabel gebruiken](landgebruik-codetabel.md){ .md-button }
[BAG-indeling per pand controleren](landgebruik-bagcontrole.md){ .md-button }

<span id="tijdelijk-vergrendelde-uitvoerbestanden"></span>

**Uitvoerbestand vergrendeld?** Sluit het bestand in QGIS en hervat met dezelfde runnaam en invoer.
