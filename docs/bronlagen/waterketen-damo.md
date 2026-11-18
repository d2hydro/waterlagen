---
editorial_status: ai
---

# Waterketen DAMO

## Beschrijving

Deze bron bevat geharmoniseerde waterketengegevens van de Nederlandse
waterschappen volgens DAMO Waterketen, met aansluiting op het
Gegevenswoordenboek Stedelijk Water (GWSW). De objecten omvatten onder meer
RWZI's, rioolgemalen, pompen, leidingen, leidingsegmenten, putten,
overnamepunten en rioleringsgebieden.

<span id="leverancier"></span>

## Herkomst

De waterschappen leveren hun waterketengegevens via het Gegevensknooppunt waterschappen (GkW) van Het Waterschapshuis. PDOK publiceert het landelijke bestand. [PDOK over Waterketen DAMO](https://api.pdok.nl/hwh/waterschappen-waterketen-damo/ogc/v1)

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
de DataStore. De laag `rwzi` bevestigt TOP10NL-zuiveringsterreinen voor de
[RWZI-gebouwclassificatie bij functioneel landgebruik](../bewerkte-lagen/functioneel-landgebruik.md#bijzondere-gebouwen-en-gemalen-stap-6).

[Waterketen DAMO downloaden](../produceren/waterketen-damo.md){ .md-button }
[API-referentie](../reference/waterketen_damo.md){ .meerlink }

## Externe verwijzingen

- [PDOK ATOM-service](https://service.pdok.nl/hwh/waterschappen-waterketen-damo/atom/index.xml)
- [Datasetfeed met downloadlink en metadata](https://service.pdok.nl/hwh/waterschappen-waterketen-damo/atom/waterschappen-waterketen-damo.xml)
- [Waterketen DAMO GeoPackage](https://service.pdok.nl/hwh/waterschappen-waterketen-damo/atom/downloads/hwh_waterketen_geopackage_DAMO.gpkg)
