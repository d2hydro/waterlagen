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
| Sloten en greppels | `waterway=ditch` | `osm_ditches` |
| Afvoerwatergangen | `waterway=drain` | `osm_drains` |
| Beken | `waterway=stream` | `osm_streams` |
| Duikers | `tunnel=culvert` | `osm_culvert` |

## Leverancier

OpenStreetMap-bijdragers.

## Dataset of service

De download gebruikt de Overpass API. Elk waterwaytype krijgt een eigen
GeoPackage onder `source_data/osm/`, met de laagnaam uit de tabel als bestandsnaam.
Duikers staan in `osm_culverts.gpkg`, laag `osm_culvert`.
De geometrie staat in het project-CRS.
Per lijn worden OSM-ID, naam, tags, OSM-peildatum en bronvermelding bewaard.
Een JSON-bestand naast het GeoPackage bewaart de selectie en downloadquery.

De opgegeven grenzen bepalen de selectie. Kruisende lijnen blijven heel.
De download van open waterlopen slaat trajecten met `tunnel` of `covered` anders dan `no` en
`location=underground` over. Ontbrekende tags gelden als open trajecten.
Duikers worden apart geselecteerd met `tunnel=culvert`, ongeacht het waterwaytype.
Hetzelfde downloadscript haalt beide selecties op.

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
