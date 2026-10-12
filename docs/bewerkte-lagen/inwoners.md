---
editorial_status: ai
---

# Inwoners

## Doel

Deze bewerking verdeelt CBS-inwoneraantallen over de geselecteerde BAG-woon-
VBO's. Het resultaat blijft op VBO-puntniveau. De bewerking bevat bewust twee
verdeelsleutels, zodat het verschil tussen het aantal CBS-huishoudens en het
aantal BAG-woon-VBO's zichtbaar blijft.

## Bronlagen

- [BAG](../bronlagen/bag.md): verblijfsobjecten met hun BAG-status,
  gebruiksdoel, identificatie, eventuele pandidentificatie en geometrie.
- [CBS Wijk- en Buurtkaart en Kerncijfers](../bronlagen/cbs.md): de laag
  `buurten` en veld `buurtcode` uit de Wijk- en Buurtkaart 2025, plus
  `aantal_inwoners`, `aantal_huishoudens` en `personenautos_totaal` uit
  StatLine.

## Werkwijze

### Woon-VBO's per CBS-buurt

De onderstaande voorbereiding van woon-VBO's wordt gedeeld met de productie
van [auto's](autos.md). Zij levert één tussenproduct met geselecteerde
BAG-verblijfsobjecten, hun CBS-buurt en het aantal woon-VBO's per buurt.

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

Voor toekomstig cloudgebruik berekent Waterlagen vervolgens een technische
`_hilbert`-kolom uit de oorspronkelijke VBO-punten en schrijft de VBO's in
oplopende Hilbert-volgorde. Hiervoor gebruikt Waterlagen de vaste landelijke
RD New-extent `(-7000, 289000, 300000, 629000)` in `EPSG:28992` en Hilbert-
level 16 (een grid van 65.536 bij 65.536 cellen). De vaste extent zorgt dat
de ruimtelijke volgorde niet verandert wanneer een datasetversie of selectie
een andere totale omvang heeft.

#### Gedeelde tussenbestanden

De bewerking schrijft twee GeoPackages onder `processed_data/vbo_buurt/`:

- `bag_vbo.gpkg`, laag `bag_vbo`, met `identificatie`,
  `pand_identificatie` wanneer beschikbaar, `status`, `gebruiksdoel`,
  `buurtcode`, `_hilbert` en de oorspronkelijke VBO-geometrie;
- `cbs_buurt.gpkg`, laag `cbs_buurt`, met de oorspronkelijke CBS-
  buurtpolygonen, `aantal_woonvbo`, `aantal_inwoners` en
  `aantal_huishoudens`, en `personenautos_totaal`.

Deze tussenbestanden bevatten nog geen verdeelde inwoners- of personenautowaarden per VBO.

### Inwoners verdelen

De bewerking koppelt de CBS-waarden op `buurtcode` aan de VBO-punten. Er vindt
geen nieuwe ruimtelijke koppeling plaats.
De technische `_hilbert`-volgorde van de gedeelde woon-VBO's blijft behouden.

Voor iedere buurt worden twee waarden berekend:

- `inwoners_obv_huishoudens` is `aantal_inwoners / aantal_huishoudens`. Deze
  volgt de oorspronkelijke methode waarin ieder woon-VBO als één huishouden
  wordt beschouwd. De som hoeft daarom niet gelijk te zijn aan het CBS-aantal
  inwoners.
- `inwoners_obv_woonvbo` is `aantal_inwoners / aantal_woonvbo`. Als alle
  woon-VBO's van een buurt aanwezig zijn, is de som hiervan wel gelijk aan het
  CBS-aantal inwoners.

Ontbrekende CBS-waarden en delingen door nul blijven leeg. Waterlagen zet deze
niet om naar nul en logt het aantal betrokken VBO's en buurten. Per buurt
controleert Waterlagen de sommen van beide verdeelmethoden.

## Uitvoer

De productie schrijft `inwoners.gpkg`, laag
`inwoners`. Deze bevat de oorspronkelijke VBO-puntgeometrie en minimaal `identificatie`,
eventueel `pand_identificatie`, `buurtcode`, `aantal_inwoners`,
`aantal_huishoudens`, `aantal_woonvbo`, `inwoners_obv_huishoudens` en
`inwoners_obv_woonvbo`, plus de technische `_hilbert`-kolom.

Bij de standaardproductie verschijnt daarnaast `inwoners.parquet` in dezelfde runmap.
Dit is standaard GeoParquet 1.1 met WKB-geometrie, een standaard bbox-covering
en Parquet-statistieken. De fysieke rijvolgorde blijft de oplopende
`_hilbert`-volgorde uit het gedeelde VBO-buurtbestand; groepen van 100.000
rijen ondersteunen daarmee ruimtelijke pruning bij een query op `bounds`.

## Aandachtspunten en beperkingen

De waarden zijn geen pand- of rasterwaarden. Personenauto's en aanvullende
correcties maken geen deel uit van deze bewerking.

Een regionale productie selecteert volledige CBS-buurten en behoudt alle
bijbehorende woon-VBO's. Daardoor blijft de verdeling per VBO gelijk aan de
landelijke berekening. De uitvoer wordt niet op de gekozen gebiedsgrens geknipt.

## Zelf produceren

Zie [Inwoners en personenauto's produceren](../produceren/inwoners-personenautos.md).
