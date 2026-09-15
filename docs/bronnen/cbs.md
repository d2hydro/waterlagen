# CBS Wijk- en Buurtkaart en Kerncijfers

## Beschrijving

Het CBS publiceert de geografische indeling in gemeenten, wijken en buurten en
StatLine-kerncijfers voor die gebieden. Waterlagen gebruikt voor de inwoners-
en personenautoanalyse uitsluitend de buurtgeometrie en drie kerncijfers op
buurtniveau.

## Leverancier

Centraal Bureau voor de Statistiek (CBS).

## Dataset of service

De [Wijk- en Buurtkaart 2025](https://www.cbs.nl/nl-nl/dossier/nederland-regionaal/geografische-data/wijk-en-buurtkaart-2025)
wordt rechtstreeks gedownload als [officieel ZIP-bestand](https://geodata.cbs.nl/files/Wijkenbuurtkaart/WijkBuurtkaart_2025_v1.zip).
Waterlagen bewaart de ongewijzigde GeoPackage hieruit als
`wijkenbuurten_2025_v1.gpkg`. Daarin is laag `buurten` met veld `buurtcode`
relevant.

De tabel [Kerncijfers wijken en buurten 2025](https://www.cbs.nl/nl-nl/cijfers/detail/86165NED)
heeft CBS-tabelcode `86165NED`. Waterlagen gebruikt de officiële
[CBS OData-interface](https://datasets.cbs.nl/odata/v1/CBS/86165NED) en
selecteert uitsluitend buurtcodes en de waarden voor aantal inwoners,
huishoudens totaal en personenauto's totaal.

## Gebruik in Waterlagen

De kaart wordt opgeslagen onder `brondata/administratieve_gebieden/`; de
selectieve StatLine-uitvoer staat onder `brondata/cbs/`. De brongegevens worden
in deze stap nog niet ruimtelijk gekoppeld of bewerkt. CBS-waarden zonder
cijfer blijven als ontbrekende waarde bewaard, met eventuele CBS-status in de
metadata van het JSON-bestand.

## Belangrijke kenmerken en beperkingen

De buurtcodes zijn CBS-codes met prefix `BU`. De kaart en StatLine-tabel horen
bij dezelfde indeling van 2025. De functie
`validate_buurtcode_systematiek` controleert expliciet of beide gedownloade
bronnen unieke CBS-buurtcodes gebruiken en of iedere StatLine-code in de
buurtgeometrie voorkomt. De kaart kan daarnaast buurtgeometrieën bevatten
waarvoor de StatLine-tabel geen rij bevat; die worden als afzonderlijk aantal
gerapporteerd.

De buurtgeometrieën worden ook gebruikt voor de ruimtelijke koppeling van
[woon-VBO's per CBS-buurt](../bewerkingen/vbo-buurt.md). In die bewerking
worden `aantal_inwoners` en `aantal_huishoudens` uit StatLine op de CBS-
buurtpolygonen bewaard, samen met het afgeleide aantal woon-VBO's. Andere
StatLine-kerncijfers worden daar nog niet aan toegevoegd.
