---
editorial_status: ai
---

# Auto's

## Doel

Deze bewerking verdeelt het CBS-aantal personenauto's per buurt gelijkmatig
over de geselecteerde BAG-woon-VBO's. Het resultaat blijft een
VBO-puntenbestand; het is geen telling van fysieke, gehele auto's op een VBO.

## Bronlagen

- [BAG](../bronlagen/bag.md): verblijfsobjecten met woonfunctie en status in gebruik.
- [CBS Wijk- en Buurtkaart en Kerncijfers](../bronlagen/cbs.md):
  `personenautos_totaal` per buurt.

## Werkwijze

### Woon-VBO's voorbereiden

De productie gebruikt dezelfde selectie en buurtkoppeling als
[inwoners](inwoners.md#woon-vbos-per-cbs-buurt). Alleen VBO's met woonfunctie
en status `Verblijfsobject in gebruik` worden meegenomen. Ieder VBO moet aan
precies één CBS-buurt zijn gekoppeld. De voorbereiding bewaart de VBO-punten,
de CBS-buurtpolygonen en het aantal geselecteerde woon-VBO's per buurt in
`processed_data/vbo_buurt/`. De volledige werkwijze en de gedeelde
tussenbestanden staan bij de inwonerslaag.

### Personenauto's verdelen

Waterlagen koppelt het CBS-totaal eenmalig op `buurtcode` aan de VBO-punten.
De waarde per VBO is `personenautos_totaal / aantal_woonvbo`. Dezelfde
vectoriële verdeelbewerking wordt gebruikt voor de inwoner-behoudende
inwonersverdeling.
De technische `_hilbert`-volgorde van de gedeelde woon-VBO's blijft behouden.

Als alle woon-VBO's van een buurt aanwezig zijn, is de som van
`personenautos` gelijk aan `personenautos_totaal`. Waterlagen controleert dit
per buurt. Ontbrekende CBS-waarden en een noemer van nul blijven leeg en
worden niet als nul geïnterpreteerd.

## Uitvoer

De productie schrijft `autos.gpkg`, laag `autos`. Deze bevat
de oorspronkelijke VBO-puntgeometrie en minimaal `identificatie`, eventueel
`pand_identificatie`, `buurtcode`, `aantal_woonvbo`,
`personenautos_totaal`, `personenautos` en de technische `_hilbert`-kolom.

Bij de standaardproductie verschijnt daarnaast `autos.parquet` in dezelfde runmap. Dit is standaard
GeoParquet 1.1 met WKB-geometrie, een standaard bbox-covering en
Parquet-statistieken. De fysieke rijvolgorde blijft de oplopende
`_hilbert`-volgorde uit het gedeelde VBO-buurtbestand; groepen van 100.000
rijen ondersteunen daarmee ruimtelijke pruning bij een query op `bounds`.

## Aandachtspunten en beperkingen

De bewerking verplaatst auto's niet naar straten of parkeerlocaties en maakt
geen pand- of rasteraggregaties.

Een regionale productie selecteert volledige CBS-buurten en behoudt alle
bijbehorende woon-VBO's. Daardoor blijft de verdeling per VBO gelijk aan de
landelijke berekening. De uitvoer wordt niet op de gekozen gebiedsgrens geknipt.

## Zelf produceren

Zie [Inwoners en personenauto's produceren](../produceren/inwoners-personenautos.md).
