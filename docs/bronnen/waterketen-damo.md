# Waterketen DAMO

## Beschrijving

Deze bron bevat geharmoniseerde waterketengegevens van de Nederlandse
waterschappen volgens DAMO Waterketen, met aansluiting op het
Gegevenswoordenboek Stedelijk Water (GWSW). De objecten omvatten onder meer
RWZI's, rioolgemalen, pompen, leidingen, leidingsegmenten, putten,
overnamepunten en rioleringsgebieden.

## Leverancier

De individuele waterschappen leveren hun gegevens via het Gegevensknooppunt
waterschappen (GkW) van Het Waterschapshuis. PDOK publiceert de landelijke bron.

## Dataset of service

Waterlagen gebruikt de actuele GeoPackage uit de ATOM-downloadservice
Waterschappen Waterketen DAMO. De bron wordt aangeboden in EPSG:28992.
De download betreft de actuele stand, geen vastgelegde jaarversie.
De feed vermeldt de licentie CC BY-SA 4.0.

Niet ieder waterschap levert de volledige gegevensset aan. Een ontbrekend
object betekent daarom niet noodzakelijk dat het object niet bestaat.
De waterschapscode bij een object verwijst naar de betreffende gegevensleverancier.

## Gebruik in Waterlagen

De bron is beschikbaar als afzonderlijke download onder `waterketen_damo` in
de DataStore. Er is nog geen afgeleide verwerking aan gekoppeld. Zie
[Waterketen DAMO downloaden](../produceren/waterketen-damo.md) voor het gebruik
en de [API-referentie](../reference/waterketen_damo.md).

## Externe verwijzingen

- [PDOK ATOM-service](https://service.pdok.nl/hwh/waterschappen-waterketen-damo/atom/index.xml)
- [Datasetfeed met downloadlink en metadata](https://service.pdok.nl/hwh/waterschappen-waterketen-damo/atom/waterschappen-waterketen-damo.xml)
- [Waterketen DAMO GeoPackage](https://service.pdok.nl/hwh/waterschappen-waterketen-damo/atom/downloads/hwh_waterketen_geopackage_DAMO.gpkg)
