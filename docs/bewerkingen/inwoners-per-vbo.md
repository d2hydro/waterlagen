# Inwoners per woon-VBO

## Doel

Deze bewerking verdeelt CBS-inwoneraantallen over de geselecteerde BAG-woon-
VBO's. Het resultaat blijft op VBO-puntniveau. De bewerking bevat bewust twee
verdeelsleutels, zodat het verschil tussen het aantal CBS-huishoudens en het
aantal BAG-woon-VBO's zichtbaar blijft.

## Invoerbronnen

- [Woon-VBO's per CBS-buurt](vbo-buurt.md): geselecteerde BAG-VBO-punten met
  `buurtcode` en CBS-buurtpolygonen met `aantal_woonvbo`.
- [CBS Wijk- en Buurtkaart en Kerncijfers](../bronnen/cbs.md):
  `aantal_inwoners` en `aantal_huishoudens` per buurt.

## Werkwijze

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

## Resultaat

De bewerking schrijft standaard `processed_data/inwoners/inwoners.gpkg`, laag
`inwoners`. Deze bevat de oorspronkelijke VBO-puntgeometrie en minimaal `identificatie`,
eventueel `pand_identificatie`, `buurtcode`, `aantal_inwoners`,
`aantal_huishoudens`, `aantal_woonvbo`, `inwoners_obv_huishoudens` en
`inwoners_obv_woonvbo`, plus de technische `_hilbert`-kolom.

Als de optie `WRITE_GEOPARQUET` in `scripts/inwoners.py` is ingeschakeld,
schrijft de bewerking daarnaast `processed_data/inwoners/inwoners.parquet`.
Dit is standaard GeoParquet 1.1 met WKB-geometrie, een standaard bbox-covering
en Parquet-statistieken. De fysieke rijvolgorde blijft de oplopende
`_hilbert`-volgorde uit het gedeelde VBO-buurtbestand; groepen van 100.000
rijen ondersteunen daarmee ruimtelijke pruning bij een query op `bounds`.

De waarden zijn geen pand- of rasterwaarden. Personenauto's en aanvullende
correcties maken geen deel uit van deze bewerking.
