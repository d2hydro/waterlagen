# OpenStreetMap-drinkwaterlocaties

## Beschrijving

Waterlagen gebruikt beoordeelde OpenStreetMap-vlakken van
drinkwaterzuiveringen om BAG-panden aan deze locaties te koppelen.

## Leverancier

OpenStreetMap-bijdragers. Waterlagen leest de gegevens via de Overpass API.

## Dataset of service

Het script haalt de OSM-vlakken op die in `drinkwater_beoordelingen.json` als
`drinkwaterzuivering` zijn geselecteerd. De uitvoer staat in
`source_data/osm/drinkwaterlocaties.gpkg`. De laag `drinkwaterproductieterrein`
bevat standaard de terreinen voor de BAG-koppeling; `terreinen_waterbedrijven`
en `gebouwcontouren` zijn controlelagen. De uitvoer vermeldt per vlak de
OSM-ID en controledatum.

## Gebruik in Waterlagen

De vlakken worden gebruikt bij
[functioneel landgebruik](../bewerkingen/functioneel-landgebruik.md).
Voor het aanmaken van het GeoPackage zie
[Functioneel landgebruik produceren](../produceren/landgebruik.md).

## Externe verwijzingen

- [OSM-betekenis van man_made=water_works](https://wiki.openstreetmap.org/wiki/Tag:man_made%3Dwater_works)
- [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API)
- [OpenStreetMap-auteursrecht en licentie](https://www.openstreetmap.org/copyright)
