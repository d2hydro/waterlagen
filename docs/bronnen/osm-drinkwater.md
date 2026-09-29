# OpenStreetMap-drinkwaterlocaties

## Beschrijving

OpenStreetMap (OSM) bevat door vrijwilligers ingetekende locaties voor
drinkwaterbereiding. Waterlagen gebruikt polygonen rond deze locaties als
aanwijzing voor gebouwen op een drinkwaterproductielocatie. De vlakken zijn
geen geverifieerde terreingrenzen en de selectie is geen volledige inventaris.

## Leverancier

OpenStreetMap-bijdragers. Waterlagen leest de gegevens via de Overpass API.

## Dataset of service

Het script selecteert in Europees Nederland objecten met
`man_made=water_works`, een naam en een naam of exploitant die overeenkomt met
een van de in het script opgenomen drinkwaterbedrijven. Het gebruikt bestaande
OSM-vlakken; voor punten zonder passend vlak wordt geen grens verzonnen.
Dubbele of twijfelachtige objecten die in het aangeleverde script zijn
benoemd, zijn expliciet uitgesloten. Die uitzonderingen zijn niet onafhankelijk
geverifieerd. De OSM-gegevens kunnen wijzigen.

Het GeoPackage onder `source_data/osm/drinkwaterlocaties.gpkg` heeft een
`drinkwaterproductieterrein`-laag voor de BAG-koppeling en afzonderlijke
lagen `terreinen_waterbedrijven` en `gebouwcontouren` voor controle.
Standaard bevat de koppellaag alleen terreinen. Losse gebouwcontouren zijn
beschikbaar als een terreinbegrenzing ontbreekt, maar zijn niet automatisch
een volledig productieterrein.

## Gebruik in Waterlagen

De vlakken worden gebruikt bij
[functioneel landgebruik](../bewerkingen/functioneel-landgebruik.md).
Voor het aanmaken van het GeoPackage zie
[Functioneel landgebruik produceren](../produceren/landgebruik.md).

## Externe verwijzingen

- [OSM-betekenis van man_made=water_works](https://wiki.openstreetmap.org/wiki/Tag:man_made%3Dwater_works)
- [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API)
- [OpenStreetMap-auteursrecht en licentie](https://www.openstreetmap.org/copyright)
