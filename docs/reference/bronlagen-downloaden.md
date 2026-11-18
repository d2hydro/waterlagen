---
editorial_status: ai
---

# Een bron downloaden met Python

[Kies en voer een script uit](gebruik.md#een-script-uitvoeren). Bij landelijke bestanden wordt de volledige bron opgehaald, ook als u later een klein gebied gebruikt.

## Voor een gebied

??? info "AHN"

    <span id="ahn"></span>

    Download de AHN4-DTM-tegels die Alkmaar-centrum raken, met resolutie 0,5 m. Hele AHN-tegels worden opgehaald; de download is groter dan het voorbeeldgebied. Het resultaat is een VRT met bijbehorende GeoTIFFs.

    [Download voorbeeldscript](voorbeelden/download_ahn.py){ .md-button .md-button--primary download="download_ahn.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_ahn.py"
    ```

    - [Over deze bron](../bronlagen/ahn.md)
    - [API-referentie](ahn.md)

??? info "BGT"

    <span id="bgt"></span>

    Vraag voor Alkmaar-centrum de objecttypen waterdeel en pand op. Het resultaat bestaat uit afzonderlijke GeoPackages in een eigen map. Dit is een klein voorbeeld van een BGT-aanvraag; de volledige landgebruikproductie gebruikt een landelijk BGT-bestand met meer objecttypen. Dit voorbeeld vervangt die bron niet.

    [Download voorbeeldscript](voorbeelden/download_bgt.py){ .md-button .md-button--primary download="download_bgt.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_bgt.py"
    ```

    - [Over deze bron](../bronlagen/bgt.md)
    - [API-referentie](bgt.md)

??? info "OSM-waterlopen en duikers"

    <span id="osm-kanalen"></span>

    Haalt kanalen, sloten, afvoerwatergangen, beken en duikers op voor de grenzen in `BOUNDS`. Standaard is dat Aa en Maas inclusief tegelbuffers.

    [Download voorbeeldscript](voorbeelden/download_osm_canals.py){ .md-button .md-button--primary download="download_osm_canals.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_osm_canals.py"
    ```

    - [Over deze bron](../bronlagen/osm-waterlopen.md)
    - [API-referentie](osm_waterlopen.md)

## Landelijke bestanden

??? info "BAG"

    <span id="bag"></span>

    Download de landelijke BAG-light als GeoPackage. Dit is een groot bestand; de download wordt niet beperkt tot Alkmaar-centrum. De productievoorbeelden gebruiken deze bron voor panden en woon-VBO's.

    [Download voorbeeldscript](voorbeelden/download_bag.py){ .md-button .md-button--primary download="download_bag.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_bag.py"
    ```

    - [Over deze bron](../bronlagen/bag.md)
    - [API-referentie](bag.md)

??? info "Bestuurlijke gebieden"

    <span id="bestuurlijke-gebieden"></span>

    Download het landelijke GeoPackage met bestuurlijke gebieden voor het standaardjaar. Het bestand bevat onder meer de landsgrens die de rasterproducties gebruiken. De gebiedsselectie volgt pas bij het verwerken.

    [Download voorbeeldscript](voorbeelden/download_bestuurlijke_gebieden.py){ .md-button .md-button--primary download="download_bestuurlijke_gebieden.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_bestuurlijke_gebieden.py"
    ```

    - [Over deze bron](../bronlagen/bestuurlijke-gebieden.md)
    - [API-referentie](administratieve_gebieden.md)

??? info "BRP"

    <span id="brp"></span>

    Zoek de nieuwste definitieve BRP-release en download het landelijke GeoPackage. Dit kan een groot bestand zijn. Een bestaand doelbestand wordt hergebruikt; de releasefeed wordt wel geraadpleegd.

    [Download voorbeeldscript](voorbeelden/download_brp.py){ .md-button .md-button--primary download="download_brp.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_brp.py"
    ```

    - [Over deze bron](../bronlagen/brp.md)
    - [API-referentie](brp.md)

??? info "CBS"

    <span id="cbs"></span>

    Download de landelijke Wijk- en Buurtkaart 2025 als GeoPackage en de benodigde kerncijfers als JSON. Ook voor Alkmaar-centrum zijn dit landelijke bronnen. De producties voor inwoners en auto's selecteren later volledige CBS-buurten.

    [Download voorbeeldscript](voorbeelden/download_cbs.py){ .md-button .md-button--primary download="download_cbs.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_cbs.py"
    ```

    - [Over deze bron](../bronlagen/cbs.md)
    - [API-referentie](cbs.md)

??? info "Dijkringen"

    <span id="dijkringen"></span>

    Download de landelijke historische dijkringen als GeoPackage. Deze bron is niet tot Alkmaar-centrum beperkt. Zie de bronpagina voor het peiljaar en de interpretatie.

    [Download voorbeeldscript](voorbeelden/download_dijkringen.py){ .md-button .md-button--primary download="download_dijkringen.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_dijkringen.py"
    ```

    - [Over deze bron](../bronlagen/dijkringen.md)
    - [API-referentie](dijkringen.md)

??? info "GKW HYDAMO"

    <span id="gkw-hydamo"></span>

    Download het landelijke HYDAMO-archief en haal het GeoPackage daaruit. Het archief kan groot zijn. De selectie van het watersysteem rond Alkmaar-centrum gebeurt in de afwateringseenhedenproductie.

    [Download voorbeeldscript](voorbeelden/download_hydamo.py){ .md-button .md-button--primary download="download_hydamo.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_hydamo.py"
    ```

    - [Over deze bron](../bronlagen/hydamo.md)
    - [API-referentie](hydamo.md)

??? info "LIWO"

    <span id="liwo"></span>

    Download het landelijke raster met overstromingsgevoelige gebieden als GeoTIFF. Deze functie haalt de volledige dekking op, ook wanneer later alleen Alkmaar-centrum wordt verwerkt.

    [Download voorbeeldscript](voorbeelden/download_liwo.py){ .md-button .md-button--primary download="download_liwo.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_liwo.py"
    ```

    - [Over deze bron](../bronlagen/liwo.md)
    - [API-referentie](liwo.md)

??? info "OSM-drinkwaterlocaties"

    <span id="osm-drinkwaterlocaties"></span>

    Haal de geometrieën van de beoordeelde drinkwaterlocaties uit OSM op en schrijf ze naar een GeoPackage. Dit is de landelijke selectie van beoordeelde locaties, geen volledige OSM-download en geen selectie rond Alkmaar-centrum.

    [Download voorbeeldscript](voorbeelden/download_osm_drinkwater.py){ .md-button .md-button--primary download="download_osm_drinkwater.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_osm_drinkwater.py"
    ```

    - [Over deze bron](../bronlagen/osm-drinkwater.md)
    - [API-referentie](osm_drinkwater.md)

??? info "Rijkswateren"

    <span id="rijkswateren"></span>

    Download het landelijke GeoPackage met voorbereide waterlopen. Het script hergebruikt een geldige lokale kopie.

    [Download voorbeeldscript](voorbeelden/download_rijkswateren.py){ .md-button .md-button--primary download="download_rijkswateren.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_rijkswateren.py"
    ```

    - [Over deze bron](../bronlagen/rijkswateren.md)
    - [API-referentie](rijkswateren.md)

??? info "TOP10NL"

    <span id="top10nl"></span>

    Download het landelijke TOP10NL-GeoPackage. Dit is een grote download die niet door het voorbeeldgebied wordt begrensd.

    [Download voorbeeldscript](voorbeelden/download_top10nl.py){ .md-button .md-button--primary download="download_top10nl.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_top10nl.py"
    ```

    - [Over deze bron](../bronlagen/top10nl.md)
    - [API-referentie](top10nl.md)

??? info "Waterketen DAMO"

    <span id="waterketen-damo"></span>

    Download de landelijke Waterketen DAMO als GeoPackage. De bron blijft landelijk; de ruimtelijke selectie volgt bij het verwerken.

    [Download voorbeeldscript](voorbeelden/download_waterketen_damo.py){ .md-button .md-button--primary download="download_waterketen_damo.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_waterketen_damo.py"
    ```

    - [Over deze bron](../bronlagen/waterketen-damo.md)
    - [API-referentie](waterketen_damo.md)

??? info "Waterschapsgrenzen"

    <span id="waterschapsgrenzen"></span>

    Download het GeoPackage met alle waterschapsgrenzen. Voor het vaste voorbeeldgebied Alkmaar-centrum is geen waterschapsgrens nodig; dit voorbeeld laat zien hoe deze bron afzonderlijk wordt opgehaald.

    [Download voorbeeldscript](voorbeelden/download_waterschapsgrenzen.py){ .md-button .md-button--primary download="download_waterschapsgrenzen.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/download_waterschapsgrenzen.py"
    ```

    - [Over deze bron](../bronlagen/waterschapsgrenzen.md)
    - [API-referentie](administratieve_gebieden.md)

## Uit een bestaand bestand

??? info "BGT-duikers voorbereiden"

    <span id="bgt-duikers-voorbereiden"></span>

    Selecteert duikervlakken voor Aa en Maas uit een [voorbereid BGT-GeoPackage](../produceren/bgt-vlakken.md#voorbereiden).

    [Download voorbeeldscript](voorbeelden/bereid_bgt_duikers.py){ .md-button .md-button--primary download="bereid_bgt_duikers.py" }

    ```python
    --8<-- "docs/reference/voorbeelden/bereid_bgt_duikers.py"
    ```
