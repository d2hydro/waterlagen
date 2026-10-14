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

Waterlagen selecteert alleen BAG-VBO's met status `Verblijfsobject in gebruik`
waarbij `woonfunctie` een van de gebruiksdoelen is. Een gecombineerd
gebruiksdoel, bijvoorbeeld `woonfunctie,kantoorfunctie`, blijft dus behouden.
De oorspronkelijke VBO-geometrie blijft de geometrie van het resultaat.

Daarna wordt ieder VBO met een ruimtelijke koppeling aan precies één CBS-buurt
gekoppeld. VBO's zonder buurt en VBO's met meerdere buurten worden gelogd en
leiden tot een fout; de bewerking kiest niet willekeurig een buurt.

Ten slotte telt Waterlagen de geselecteerde woon-VBO's per `buurtcode`. Dit
aantal wordt aan de CBS-buurtpolygonen toegevoegd, niet aan ieder afzonderlijk
VBO.

### Ruimtelijke sortering

Voor toekomstig cloudgebruik berekent Waterlagen vervolgens een technische
`_hilbert`-kolom uit de oorspronkelijke VBO-punten en schrijft de VBO's in
oplopende Hilbert-volgorde. Hiervoor gebruikt Waterlagen de vaste landelijke
RD New-extent `(-7000, 289000, 300000, 629000)` in `EPSG:28992` en Hilbert-
level 16 (een grid van 65.536 bij 65.536 cellen). De vaste extent zorgt dat
de ruimtelijke volgorde niet verandert wanneer een datasetversie of selectie
een andere totale omvang heeft.

Zie voor de Hilbert-volgorde en de betekenis van de begrenzing en het detailniveau de [toelichting op Hilbert-afstanden](https://dask-geopandas.readthedocs.io/en/stable/docs/reference/api/dask_geopandas.GeoSeries.hilbert_distance.html).

## Uitvoer

De bewerking schrijft twee GeoPackages onder `processed_data/vbo_buurt/`:

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
