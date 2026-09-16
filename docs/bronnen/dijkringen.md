# Dijkringen

## Beschrijving

De historische dijkringenbron bevat de laag `dijkring_v_2012`. Waterlagen
gebruikt deze geometrieën als begrenzing voor classificaties binnen en buiten
een dijkring.

## Leverancier

Rijkswaterstaat.

## Dataset of service

Waterlagen vraagt de OGC WFS van Rijkswaterstaat op. Als die download niet
beschikbaar is, gebruikt het pakket de ArcGIS MapServer als technische fallback.

## Gebruik in Waterlagen

Dijkringen zijn invoer voor [functioneel landgebruik](../bewerkingen/functioneel-landgebruik.md).

## Externe verwijzingen

- [Dijkringenhistorie WFS](https://geo.rijkswaterstaat.nl/services/ogc/gdr/dijkringen_historie/ows?service=WFS&version=2.0.0&request=GetCapabilities)
- [Dijkringenhistorie MapServer](https://geo.rijkswaterstaat.nl/arcgis/rest/services/GDR/dijkringen_historie/MapServer)
