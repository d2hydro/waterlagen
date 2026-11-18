---
editorial_status: ai
---

# Dijkringen

## Beschrijving

De historische dijkringenbron bevat de laag `dijkring_v_2012`.

<span id="leverancier"></span>

## Herkomst

Rijkswaterstaat is de data-eigenaar van de historische laag `dijkring_v_2012`. [Registratie van de dataset](https://data.overheid.nl/en/dataset/16386-dijkring-v)

## Dataset of service

Waterlagen vraagt de OGC WFS van Rijkswaterstaat op. Als die download niet
beschikbaar is, gebruikt het pakket de ArcGIS MapServer als technische fallback.

## Gebruik in Waterlagen

De downloader blijft beschikbaar als afzonderlijke bron. Voor
[functioneel landgebruik](../bewerkte-lagen/functioneel-landgebruik.md) wordt
uitsluitend de [LIWO-selectie](../bewerkte-lagen/functioneel-landgebruik.md#liwo-selectie) gebruikt.

## Externe verwijzingen

- [Dijkringenhistorie WFS](https://geo.rijkswaterstaat.nl/services/ogc/gdr/dijkringen_historie/ows?service=WFS&version=2.0.0&request=GetCapabilities)
- [Dijkringenhistorie MapServer](https://geo.rijkswaterstaat.nl/arcgis/rest/services/GDR/dijkringen_historie/MapServer)
