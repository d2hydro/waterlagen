# BAG

## Beschrijving

De Basisregistratie Adressen en Gebouwen (BAG) bevat gegevens over onder meer
panden en verblijfsobjecten. Waterlagen leest voor zijn workflows deze twee
objecttypen.

## Leverancier

Kadaster (Landelijke Voorziening BAG), ontsloten via PDOK.

## Dataset of service

Waterlagen kan een gebiedsselectie ophalen via de BAG-WFS of een landelijke
`bag-light.gpkg` downloaden en daaruit lezen. Een WFS-verzoek is in Waterlagen
begrensd op 50.000 objecten; gebruik voor grotere selecties het landelijke
GeoPackage.

## Gebruik in Waterlagen

BAG-panden zijn invoer voor [BAG-vloerpeilen](../bewerkingen/bag-vloerpeilen.md)
en voor [functioneel landgebruik](../bewerkingen/functioneel-landgebruik.md).
Voor de verwerking van inwoners en personenauto's worden uitsluitend
verblijfsobjecten met woonfunctie en status in gebruik gebruikt; zie
[Woon-VBO's per CBS-buurt](../bewerkingen/vbo-buurt.md).

## Externe verwijzingen

- [BAG op PDOK](https://www.pdok.nl/introductie/-/article/basisregistratie-adressen-en-gebouwen-ba-1)
- [BAG-WFS](https://service.pdok.nl/lv/bag/wfs/v2_0?service=WFS&request=GetCapabilities)
- [BAG Atom-download](https://service.pdok.nl/lv/bag/atom/index.xml)
