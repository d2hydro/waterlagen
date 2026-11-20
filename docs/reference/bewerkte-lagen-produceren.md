---
editorial_status: ai
---

# Een kaartlaag berekenen met Python

Open het voorbeeld voor uw kaartlaag. Wijzigt u de invoer of instellingen? Kies dan in het script een nieuwe naam voor `EXPERIMENT`, zodat de resultaten apart worden opgeslagen. [Een script uitvoeren](gebruik.md#een-script-uitvoeren)

??? info "Afwateringseenheden"

    <span id="afwateringseenheden"></span>

    Berekent afwateringseenheden voor Alkmaar-centrum met een buffer van 2 km. De uitvoer wordt op het gebied geknipt. Controleer de duikerkoppelingen in `controle.gpkg`. Vanuit de broncoderepository gebruikt u de omgeving `afwateringseenheden` voor PCRaster.

    [Download voorbeeldscript](voorbeelden/produceer_afwateringseenheden.py){ .md-button .md-button--primary download="produceer_afwateringseenheden.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/produceer_afwateringseenheden.py"
    ```

    - [Betekenis van de laag](../bewerkte-lagen/afwateringseenheden.md)
    - [API-referentie](afwateringseenheden.md)

??? info "Functioneel landgebruik"

    <span id="functioneel-landgebruik"></span>

    Maakt een raster van 1 × 1 km voor Alkmaar-centrum. Sommige bronnen worden landelijk opgehaald. Gebruik voor een aansluitende DEM-berekening de standaardresolutie van 0,5 m en bewaar de gebouwgegevens.

    [Download voorbeeldscript](voorbeelden/produceer_functioneel_landgebruik.py){ .md-button .md-button--primary download="produceer_functioneel_landgebruik.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/produceer_functioneel_landgebruik.py"
    ```

    - [Betekenis van de laag](../bewerkte-lagen/functioneel-landgebruik.md)
    - [API-referentie](functioneel_landgebruik.md)

??? info "Hoogtemodel"

    <span id="hoogtemodel"></span>

    Voer eerst het voorbeeld voor functioneel landgebruik uit. Kies die uitvoer met `LANDUSE_EXPERIMENT`. De gebouwcontext moet minstens de maximale zoekafstand voor gebouwhoogtes dekken. AHN en landgebruik moeten dezelfde resolutie en pixeluitlijning hebben.

    [Download voorbeeldscript](voorbeelden/produceer_dem.py){ .md-button .md-button--primary download="produceer_dem.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/produceer_dem.py"
    ```

    - [Betekenis van de laag](../bewerkte-lagen/dem.md)
    - [API-referentie](dem.md)

??? info "Inwoners"

    <span id="inwoners"></span>

    Verdeelt inwoners over verblijfsobjecten met woonfunctie volgens twee methoden. Het script gebruikt dezelfde landelijke BAG/CBS-voorbereiding als het autovoorbeeld en schrijft `inwoners.gpkg`.

    [Download voorbeeldscript](voorbeelden/produceer_inwoners.py){ .md-button .md-button--primary download="produceer_inwoners.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/produceer_inwoners.py"
    ```

    - [Betekenis van de laag](../bewerkte-lagen/inwoners.md)
    - [API-referentie](inwoners.md)
    - [Gedeelde voorbereiding](vbo_buurt.md)

??? info "Auto's"

    <span id="autos"></span>

    Verdeelt auto’s over verblijfsobjecten met woonfunctie. BAG en CBS worden landelijk voorbereid. Behoud bij de berekening alle woonverblijfsobjecten van elke geselecteerde buurt.

    [Download voorbeeldscript](voorbeelden/produceer_autos.py){ .md-button .md-button--primary download="produceer_autos.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/produceer_autos.py"
    ```

    - [Betekenis van de laag](../bewerkte-lagen/autos.md)
    - [API-referentie](autos.md)
    - [Gedeelde voorbereiding](vbo_buurt.md)

## Bron voorbereiden

??? info "BGT-vlakken"

    <span id="bgt-vlakken"></span>

    Zet een bestaande landelijke BGT-ZIP om naar `bgt.gpkg`. [Benodigde invoer](../produceren/bgt-vlakken.md#voorbereiden)

    [Download voorbeeldscript](voorbeelden/bereid_bgt_vlakken.py){ .md-button .md-button--primary download="bereid_bgt_vlakken.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/bereid_bgt_vlakken.py"
    ```
