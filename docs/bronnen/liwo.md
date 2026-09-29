# LIWO overstromingsgevoelige gebieden

## Beschrijving

De laag `LIWO_Basis:Overstromingsgevoelige_gebieden_grote_en_regionale_wateren`
onderscheidt overstromingsgevoelige gebieden vanuit grote en regionale wateren.
De legenda bevat zeven waarden (0 tot en met 6).

## Leverancier

Landelijk Informatiesysteem Water en Overstromingen (LIWO), ontsloten via
Basisinformatie Overstromingen.

## Dataset of service

De WMS levert kaartbeelden en de legenda. Waterlagen downloadt de oorspronkelijke
klassewaarden via WCS 2.0.1 als enkelbands GeoTIFF. De gecontroleerde dekking heeft
25 × 25 m cellen in EPSG:28992, 10.921 kolommen en 12.523 rijen. De begrenzing is
`(11825, 306750, 284850, 619825)`.

De relevante legendawaarden zijn:

| Waarde | Omschrijving uit de legenda |
| --- | --- |
| 1 | Buitendijks gebied (niet door primaire keringen beschermd) |
| 6 | Extra overstroombaar gebied volgens regionaal onbeschermd |

Het gaat om de actuele servicedekking, niet om een vastgelegde jaarversie.
Rastergrenzen volgen het 25 m grid en zijn geen nauwkeurige perceelgrenzen.

## Gebruik in Waterlagen

De bron wordt gebruikt voor de [selectie van overstromingsgevoelige gebieden](../bewerkingen/liwo-selectie.md).

## Externe verwijzingen

- [WMS-capabilities](https://basisinformatie-overstromingen.nl/geoserver/ows?service=wms&request=GetCapabilities)
- [WCS-dekkingsbeschrijving](https://basisinformatie-overstromingen.nl/geoserver/ows?service=WCS&version=2.0.1&request=DescribeCoverage&coverageId=LIWO_Basis__Overstromingsgevoelige_gebieden_grote_en_regionale_wateren)
- [Legenda met klassewaarden](https://basisinformatie-overstromingen.nl/geoserver/ows?service=WMS&version=1.1.1&request=GetLegendGraphic&layer=LIWO_Basis:Overstromingsgevoelige_gebieden_grote_en_regionale_wateren&format=application/json)
