---
editorial_status: human
---

# Auto's

## Doel

Deze bewerking verdeelt het aantal personenauto's vanuit de CBS buurtstatistiek buurt gelijkmatig over de verblijfsobjecten (VBO's) met functie wonen binnen de buurt. Het resultaat wordt op de punt-geometrie van een verblijfsobject weergegeven

## Bronlagen

| Bron | Gebruik |
| --- | --- |
| [BAG](../bronlagen/bag.md) | Verblijfsobjecten met woonfunctie en status in gebruik. |
| [CBS Wijk- en Buurtkaart en Kerncijfers](../bronlagen/cbs.md) | `personenautos_totaal` per buurt. |

## Werkwijze

Hieronder wordt het berekenen van deze laag beschreven

### verblijfsobjecten met woonfunctie (Woon-VBO's) voorbereiden

Het selecteren van Woon-VBO's staat beschreven bij [Woon-VBO's per CBS-buurt](vbo-buurt.md). Deze voorbewerkte laag wordt hergebruikt wanneer zowel inwoners als autos worden berekend.

### Personenauto's verdelen

Het CBS-aantal personenauto’s wordt gelijkmatig verdeeld over de woon-VBO’s in een buurt.

Bijvoorbeeld: een buurt heeft 70 personenauto’s en 50 woon-VBO’s. Ieder woon-VBO krijgt dan de waarde 1,4 in personenautos. Samen tellen de 50 waarden in de woon-VBOs in een buurt op tot het CBS-totaal van 70. Het gaat om een geschatte verdeling, niet om het werkelijke autobezit per adres.

Er zijn twee uitzonderingen:

- Het CBS-aantal publiceert geen aantal auto's voor een buurt (waarde is null): de waarde per VBO blijft leeg. Onbekend betekent immers niet dat er geen auto’s zijn.
- Er liggen geen woon-VBO's in de buurt: het CBS-aantal kan niet worden verdeeld, omdat delen door nul niet mogelijk is. Er kan dan geen waarde per VBO worden berekend.

## Uitvoer

De productie schrijft `autos.gpkg`, laag `autos`. Deze bevat
de oorspronkelijke VBO-puntgeometrie en minimaal `identificatie`, eventueel
`pand_identificatie`, `buurtcode`, `aantal_woonvbo`,
`personenautos_totaal`, `personenautos`. 

De kolom `__hilbert` bevat de [ruimtelijke sortering](vbo-buurt.md#ruimtelijke-sortering) die gebruikt kan worden om uitsnedes via de cloud uit te lezen.

Bij de standaardproductie verschijnt daarnaast `autos.parquet` in dezelfde runmap bedoeld voor een cloud-native gebruik van deze laag.

## Aandachtspunten en beperkingen

De bewerking verplaatst auto's niet naar straten of parkeerlocaties.

Een een nationale, of regionale (bijvoorbeeld voor 1 waterschap) selecteert volledige CBS-buurten en behoudt alle bijbehorende woon-VBO's voor het betreffende gebied. Daardoor blijft de verdeling per VBO gelijk aan de landelijke berekening. De uitvoer wordt niet op de gekozen gebiedsgrens geknipt.

## Zelf produceren

Zie [Inwoners en personenauto's produceren](../produceren/inwoners-personenautos.md).
