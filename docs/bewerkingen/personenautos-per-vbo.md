# Personenauto's per woon-VBO

## Doel

Deze bewerking verdeelt het CBS-aantal personenauto's per buurt gelijkmatig
over de geselecteerde BAG-woon-VBO's. Het resultaat blijft een
VBO-puntenbestand; het is geen telling van fysieke, gehele auto's op een VBO.

## Invoerbronnen

- [Woon-VBO's per CBS-buurt](vbo-buurt.md): geselecteerde BAG-VBO-punten met
  `buurtcode` en het aantal woon-VBO's per buurt.
- [CBS Wijk- en Buurtkaart en Kerncijfers](../bronnen/cbs.md):
  `personenautos_totaal` per buurt.

## Werkwijze

Waterlagen koppelt het CBS-totaal eenmalig op `buurtcode` aan de VBO-punten.
De waarde per VBO is `personenautos_totaal / aantal_woonvbo`. Dezelfde
vectoriële verdeelbewerking wordt gebruikt voor de inwoner-behoudende
inwonersverdeling.

Als alle woon-VBO's van een buurt aanwezig zijn, is de som van
`personenautos` gelijk aan `personenautos_totaal`. Waterlagen controleert dit
per buurt. Ontbrekende CBS-waarden en een noemer van nul blijven leeg en
worden niet als nul geïnterpreteerd.

## Resultaat

De bewerking schrijft `processed_data/autos/autos.gpkg`, laag `autos`. Deze bevat
de oorspronkelijke VBO-puntgeometrie en minimaal `identificatie`, eventueel
`pand_identificatie`, `buurtcode`, `aantal_woonvbo`,
`personenautos_totaal` en `personenautos`.

De bewerking verplaatst auto's niet naar straten of parkeerlocaties en maakt
geen pand- of rasteraggregaties.
