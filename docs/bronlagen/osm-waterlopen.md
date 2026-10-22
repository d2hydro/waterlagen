---
editorial_status: ai
---

# OpenStreetMap-waterlopen

## Beschrijving

OpenStreetMap bevat waterlijnen en duikertrajecten. Voor aanvullende brandlagen
kunnen de volgende selecties worden aangeleverd:

| Selectie | OSM-kenmerk | Voorbeeldlaag |
| --- | --- | --- |
| Kanalen | `waterway=canal` | `osm_canals` |
| Duikers | `tunnel=culvert` | `osm_culvert` |

## Leverancier

OpenStreetMap-bijdragers.

## Dataset of service

De kanaaldownload gebruikt de Overpass API en schrijft
`source_data/osm/osm_canals.gpkg`, laag `osm_canals`, in het project-CRS.
Per lijn worden OSM-ID, naam, tags, OSM-peildatum en bronvermelding bewaard.
Een JSON-bestand naast het GeoPackage bewaart de selectie en downloadquery.

De opgegeven grenzen bepalen de selectie. Kruisende lijnen blijven heel.
De download slaat trajecten met `tunnel` of `covered` anders dan `no` en
`location=underground` over. Ontbrekende tags gelden als open trajecten.
Duikers worden via deze functie niet gedownload.

De kanaalselectie omvat geen andere OSM-waterwaytypen, zoals sloten en beken.
De registratie geeft geen garantie dat lijnen hydraulisch verbonden zijn.

## Gebruik in Waterlagen

Optionele invoer voor [afwateringseenheden](../bewerkte-lagen/afwateringseenheden.md).
Zie de [TOML-configuratie](../produceren/afwateringseenheden.md#toml-configuratie)
voor het inschakelen en de voorbeeldinstellingen.
Het [downloadvoorbeeld](../reference/bronlagen-downloaden.md#osm-kanalen)
selecteert Aa en Maas inclusief tegelbuffers. De TOML downloadt niet zelf.

## Externe verwijzingen

- [OSM: waterway=canal](https://wiki.openstreetmap.org/wiki/Tag:waterway%3Dcanal)
- [OSM: tunnel=culvert](https://wiki.openstreetmap.org/wiki/Tag:tunnel%3Dculvert)
- [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API)
- [Overpass interpreter](https://overpass-api.de/api/interpreter)
- [OSM-bronvermelding en ODbL](https://www.openstreetmap.org/copyright)
