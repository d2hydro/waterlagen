# AHN

## Beschrijving

Het Actueel Hoogtebestand Nederland (AHN) is een digitale hoogtekaart van
Nederland. Waterlagen gebruikt DTM (maaiveldmodel) en DSM (oppervlaktemodel)
als GeoTIFF-rastertegels, met 0,5 m of 5 m resolutie.

## Leverancier

AHN.

## Dataset of service

Waterlagen leest de kaartbladindex van AHN en downloadt geselecteerde tegels.
Voor AHN2 tot en met AHN5 gebruikt de index kaartbladen; AHN6 gebruikt een
eigen bladwijzer. De gekozen versie, het model en de resolutie bepalen de bronbestanden.

## Gebruik in Waterlagen

AHN is invoer voor [AHN interpoleren](../bewerkingen/ahn-interpoleren.md),
[BAG-vloerpeilen](../bewerkingen/bag-vloerpeilen.md) en
[afwateringseenheden](../bewerkingen/afwateringseenheden.md).

## Externe verwijzingen

- [AHN Dataroom](https://www.ahn.nl/dataroom)
- [AHN-bladwijzer voor AHN2–AHN5](https://basisdata.nl/hwh-ahn/AUX/bladwijzer.gpkg)
- [AHN6-bladwijzer](https://basisdata.nl/hwh-ahn/AUX/bladwijzer_AHN6.gpkg)
