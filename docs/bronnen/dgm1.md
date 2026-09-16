# DGM1 Nordrhein-Westfalen

## Beschrijving

DGM1 is het digitale maaiveldmodel van Nordrhein-Westfalen, geleverd als
GeoTIFF-rasters met een resolutie van 1 m en tegels van 1 × 1 km.

## Leverancier

Geobasis NRW, via OpenGeodata Nordrhein-Westfalen.

## Dataset of service

Waterlagen leest de openbare bestandsindex en kiest per tegel het nieuwste
vermelde jaar. De originele rasters gebruiken UTM32 (`EPSG:25832`) en
DHHN2016-hoogten. De download behoudt deze stelsels; de bestanden zijn dus niet
direct uitwisselbaar met AHN in RD/NAP.

## Gebruik in Waterlagen

DGM1 kan AHN aanvullen in een eigen workflow voor
[afwateringseenheden](../bewerkingen/afwateringseenheden.md#optioneel-duits-hoogtemodel).
Het Aa en Maas-script gebruikt uitsluitend AHN. Zie
[DGM1 downloaden](../produceren/dgm1.md) voor selectie en uitvoering en de
[API-referentie](../reference/dgm1.md) voor de Python-interface.

## Externe verwijzingen

- [NRW-bestandsindex voor DGM1 GeoTIFFs](https://www.opengeodata.nrw.de/produkte/geobasis/hm/dgm1_tiff/dgm1_tiff/)
