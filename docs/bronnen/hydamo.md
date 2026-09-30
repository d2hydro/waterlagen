# GKW HYDAMO

## Beschrijving

De GKW HYDAMO-download bevat een landelijke GeoPackage met HyDAMO-lagen,
waaronder hydroobjecten en puntobjecten.

## Leverancier

De repository identificeert deze bron als GKW HYDAMO. Het package-endpoint bevat
geen afzonderlijke leveranciersmetadata; bevestig eigenaar, versie en
gebruiksvoorwaarden bij een inhoudelijke publicatie.

## Dataset of service

Waterlagen download een ZIP-package, valideert de GeoPackage daarin en schrijft
deze lokaal als `hydamo.gpkg`.

## Gebruik in Waterlagen

GKW HYDAMO is invoer voor [afwateringseenheden](../bewerkingen/afwateringseenheden.md)
en de gemaalklassen bij [functioneel landgebruik](../bewerkingen/functioneel-landgebruik.md).
Daarvoor worden de puntlaag `gemaal`, `globalid` en `maximalecapaciteit` gebruikt.
Volgens het DAMO-objectenhandboek is de capaciteit van een gemaal uitgedrukt
in m³/minuut. De afzonderlijke laag `pomp` wordt hierbij niet opgeteld.
Een ontbrekende capaciteit is geen capaciteit van nul; de bron kan onvolledig zijn.

## Externe verwijzingen

- [GKW HYDAMO-package](https://nhipackages.blob.core.windows.net/packages/gkw-hydamo-package.zip)
- [DAMO-objectenhandboek: Gemaal, inclusief eenheid maximaleCapaciteit](https://damo.hetwaterschapshuis.nl/DAMO%202.4/Objectenhandboek%20DAMO%202.4/html/Gemaal.html)
