---
editorial_status: human
---

# Auto's

## Doel

De kaart geeft per verblijfsobject met woonfunctie (woon-VBO) een schatting van het aantal personenauto’s, op basis van het CBS-totaal voor de buurt.

<span id="zelf-produceren"></span>

[Deze personenautokaart maken](../produceren/inwoners-personenautos.md){ .md-button .md-button--primary }

## Bronlagen

[BAG](../bronlagen/bag.md) levert de woon-VBO’s met status in gebruik. [CBS](../bronlagen/cbs.md) levert de buurtgrenzen en het aantal personenauto’s.

## Werkwijze

[Koppel de woon-VBO’s aan hun CBS-buurt](vbo-buurt.md) en deel het aantal personenauto’s door het aantal woon-VBO’s. Bij 70 auto’s en 50 woon-VBO’s krijgt elk punt de waarde 1,4.

Ontbreekt het CBS-aantal, dan blijft de waarde leeg. Zonder woon-VBO’s kan het buurttotaal niet worden verdeeld.

## Uitvoer

`autos.gpkg` (laag `autos`) en `autos.parquet` bevatten de oorspronkelijke VBO-punten.

??? info "Welke velden staan in de uitvoer?"

    Elk punt heeft `identificatie`, `buurtcode`, `aantal_woonvbo`, `personenautos_totaal` en `personenautos`. Waar beschikbaar is ook `pand_identificatie` opgenomen. De [ruimtelijke sorteersleutel](vbo-buurt.md#ruimtelijke-sortering) is `_hilbert`.

## Aandachtspunten en beperkingen

De punten geven een schatting per woon-VBO. Ze geven geen parkeerlocaties aan. Een regionale selectie omvat hele CBS-buurten. Daardoor kunnen punten buiten de gekozen grens liggen en blijft de waarde per punt gelijk aan die in de landelijke kaart.
