---
editorial_status: human
---

# Inwoners

## Doel

De kaart geeft per verblijfsobject met woonfunctie (woon-VBO) een schatting van het aantal inwoners, op basis van het CBS-totaal voor de buurt.

<span id="zelf-produceren"></span>

[Deze inwonerskaart maken](../produceren/inwoners-personenautos.md){ .md-button .md-button--primary }

## Bronlagen

[BAG](../bronlagen/bag.md) levert de woon-VBO’s met status in gebruik. [CBS](../bronlagen/cbs.md) levert de buurtgrenzen en de aantallen inwoners en huishoudens.

## Werkwijze

[Koppel de woon-VBO’s aan hun CBS-buurt](vbo-buurt.md). Elk punt in dezelfde buurt krijgt twee schattingen:

- `inwoners_obv_woonvbo` deelt het aantal inwoners door het aantal woon-VBO’s. Samen tellen de punten op tot het CBS-buurttotaal als alle woon-VBO’s aanwezig zijn.
- `inwoners_obv_huishoudens` deelt het aantal inwoners door het aantal huishoudens. Elk woon-VBO telt als één huishouden. Het totaal over alle punten kan daardoor afwijken.

??? info "Rekenvoorbeeld met 100 inwoners"

    Bij 50 woon-VBO’s krijgt elk punt 2 inwoners, samen 100. Zijn er 40 huishoudens, dan geeft de huishoudensmethode 2,5 inwoners per punt, samen 125.

Ontbreekt een benodigd CBS-cijfer, dan blijft die uitkomst leeg. Bij nul huishoudens blijft de huishoudensschatting leeg. Zonder woon-VBO’s zijn er geen punten om het buurttotaal over te verdelen.

## Uitvoer

`inwoners.gpkg` (laag `inwoners`) en `inwoners.parquet` bevatten de oorspronkelijke VBO-punten.

??? info "Welke velden staan in de uitvoer?"

    Elk punt heeft `identificatie`, `buurtcode`, `aantal_woonvbo`, `aantal_inwoners`, `aantal_huishoudens`, `inwoners_obv_huishoudens` en `inwoners_obv_woonvbo`. Waar beschikbaar is ook `pand_identificatie` opgenomen. De [ruimtelijke sorteersleutel](vbo-buurt.md#ruimtelijke-sortering) is `_hilbert`.

## Aandachtspunten en beperkingen

De uitkomsten zijn schattingen per woon-VBO. Een regionale selectie omvat hele CBS-buurten. Daardoor kunnen punten buiten de gekozen grens liggen en blijft de waarde per punt gelijk aan die in de landelijke kaart.
