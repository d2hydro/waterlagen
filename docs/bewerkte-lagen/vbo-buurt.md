---
editorial_status: ai
---

# Woon-VBO's per CBS-buurt

## Doel

Deze voorbereiding maakt het gedeelde tussenproduct voor [inwoners](inwoners.md)
en [auto's](autos.md). Het bevat geselecteerde BAG-verblijfsobjecten met
woonfunctie, de CBS-buurt waarin ieder VBO ligt en het aantal woon-VBO's per buurt.

## Bronlagen

- [BAG](../bronlagen/bag.md): verblijfsobjecten met hun BAG-status,
  gebruiksdoel, identificatie, eventuele pandidentificatie en geometrie.
- [CBS Wijk- en Buurtkaart en Kerncijfers](../bronlagen/cbs.md): de laag
  `buurten` en veld `buurtcode` uit de Wijk- en Buurtkaart 2025, plus
  `aantal_inwoners`, `aantal_huishoudens` en `personenautos_totaal` uit
  StatLine.

## Werkwijze

### Selectie en buurtkoppeling

Selecteer verblijfsobjecten met status `Verblijfsobject in gebruik` en `woonfunctie` als een van de gebruiksdoelen. Behoud de oorspronkelijke puntgeometrie. Koppel elk punt aan precies één buurt. Bij nul of meerdere matches stopt de berekening met een melding. Tel de punten per `buurtcode` en voeg het aantal toe aan de buurtpolygonen.

### Ruimtelijke sortering

??? info "Hoe werkt de Hilbert-sorteersleutel?"

    De VBO-punten worden ruimtelijk gesorteerd op hun `_hilbert`-waarde. De berekening gebruikt in `EPSG:28992` een vaste landelijke begrenzing `(-7000, 289000, 300000, 629000)` en niveau 16 (65.536 × 65.536 cellen). Daardoor houdt een punt dezelfde sorteersleutel bij een andere gebiedsselectie of datasetversie. Zie de [toelichting op Hilbert-afstanden](https://dask-geopandas.readthedocs.io/en/stable/docs/reference/api/dask_geopandas.GeoSeries.hilbert_distance.html).

## Uitvoer

De woon-VBO’s en de buurtpolygonen staan in `bag_vbo.gpkg` en `cbs_buurt.gpkg` onder `processed_data/vbo_buurt/`.

??? info "GeoPackages en velden"

    - `bag_vbo.gpkg`, laag `bag_vbo`, met `identificatie`,
      `pand_identificatie` wanneer beschikbaar, `status`, `gebruiksdoel`,
      `buurtcode`, `_hilbert` en de oorspronkelijke VBO-geometrie;
    - `cbs_buurt.gpkg`, laag `cbs_buurt`, met de oorspronkelijke CBS-
      buurtpolygonen, `aantal_woonvbo`, `aantal_inwoners` en
      `aantal_huishoudens`, en `personenautos_totaal`.

    Deze tussenbestanden bevatten nog geen verdeelde inwoners- of personenautowaarden per VBO.

## Zelf produceren

De voorbereiding is onderdeel van [Inwoners en personenauto's produceren](../produceren/inwoners-personenautos.md).
Beide workflows hergebruiken hetzelfde tussenproduct zolang de bronidentiteit overeenkomt.
