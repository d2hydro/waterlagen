---
editorial_status: human
---

# Inwoners

## Doel

Deze bewerking verdeelt het aantal inwoners vanuit de CBS buurtstatistiek buurt gelijkmatig over de verblijfsobjecten (VBO's) met functie wonen binnen de buurt. Het resultaat wordt op de punt-geometrie van een verblijfsobject weergegeven

## Bronlagen

De volgende bronnen worden gebruikt in deze berekening
- [BAG](../bronlagen/bag.md): verblijfsobjecten met woonfunctie en status in gebruik.
- [CBS Wijk- en Buurtkaart en Kerncijfers](../bronlagen/cbs.md):
  `personenautos_totaal` per buurt.

## Werkwijze

Hieronder wordt het berekenen van deze laag beschreven

### Woon-VBO's voorbereiden

De selectie van woon-VBO's, de koppeling aan CBS-buurten en de gedeelde
tussenbestanden staan beschreven bij [Woon-VBO's per CBS-buurt](vbo-buurt.md).
Deze voorbereiding wordt gedeeld met de productie van [auto's](autos.md).

### Inwoners verdelen

Voor iedere buurt worden twee waarden berekend:

- `inwoners_obv_huishoudens` is `aantal_inwoners / aantal_huishoudens`. Deze
  volgt de oorspronkelijke methode waarin ieder woon-VBO als één huishouden
  wordt beschouwd. De som hoeft daarom niet gelijk te zijn aan het CBS-aantal
  inwoners.
- `inwoners_obv_woonvbo` is `aantal_inwoners / aantal_woonvbo`. Als alle
  woon-VBO's van een buurt aanwezig zijn, is de som hiervan wel gelijk aan het
  CBS-aantal inwoners.

Het CBS-aantal inwoners wordt op twee manieren verdeeld over de woon-VBO’s in een buurt: op basis van het aantal woon-VBO’s en op basis van het aantal huishoudens.

Bijvoorbeeld: een buurt heeft 100 inwoners, 50 woon-VBO’s en 40 huishoudens.

- Verdeling over woon-VBO’s: ieder woon-VBO krijgt 100 ÷ 50 = 2 inwoners. Samen tellen de waarden op tot het CBS-totaal van 100 inwoners.
- Verdeling op basis van huishoudens: de gemiddelde huishoudensgrootte is 100 ÷ 40 = 2,5 personen. Ieder woon-VBO krijgt daarom 2,5 inwoners. Samen tellen de waarden op tot 125 inwoners. Het totaal wijkt hier af van het CBS-totaal, omdat het aantal woon-VBO’s niet gelijk is aan het aantal huishoudens.

Beide methoden geven een geschatte verdeling, niet het werkelijke aantal bewoners per adres.

Er zijn twee uitzonderingen:

- Als benodigde CBS-gegevens ontbreken, blijft de bijbehorende uitkomst leeg. Onbekend betekent niet dat er geen inwoners zijn.
- Als het aantal huishoudens nul is, kan de verdeling op basis van huishoudens niet worden berekend. Zonder woon-VBO’s zijn er geen objecten waarover de inwoners kunnen worden verdeeld.

## Uitvoer

De productie schrijft `inwoners.gpkg`, laag
`inwoners`. Deze bevat de oorspronkelijke VBO-puntgeometrie en minimaal `identificatie`,
eventueel `pand_identificatie`, `buurtcode`, `aantal_inwoners`,
`aantal_huishoudens`, `aantal_woonvbo`, `inwoners_obv_huishoudens` en
`inwoners_obv_woonvbo`

De kolom `__hilbert` bevat de [ruimtelijke sortering](vbo-buurt.md#ruimtelijke-sortering) die gebruikt kan worden om uitsnedes via de cloud uit te lezen.

Bij de standaardproductie verschijnt daarnaast `inwoners.parquet` in dezelfde runmap bedoeld voor een cloud-native gebruik van deze laag.

## Aandachtspunten en beperkingen

Een een nationale, of regionale (bijvoorbeeld voor 1 waterschap) selecteert volledige CBS-buurten en behoudt alle bijbehorende woon-VBO's voor het betreffende gebied. Daardoor blijft de verdeling per VBO gelijk aan de landelijke berekening. De uitvoer wordt niet op de gekozen gebiedsgrens geknipt.

## Zelf produceren

Zie [Inwoners en personenauto's produceren](../produceren/inwoners-personenautos.md).
