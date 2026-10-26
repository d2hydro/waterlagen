---
editorial_status: ai
---

# GKW HYDAMO

## Beschrijving

De GKW HYDAMO-download bevat een landelijke GeoPackage met HyDAMO-lagen,
waaronder hydroobjecten, puntobjecten en duikers, sifons en hevels.

## Leverancier

De repository identificeert deze bron als GKW HYDAMO. Het package-endpoint bevat
geen afzonderlijke leveranciersmetadata; bevestig eigenaar, versie en
gebruiksvoorwaarden bij een inhoudelijke publicatie.

## Dataset of service

Waterlagen download een ZIP-package, valideert de GeoPackage daarin en schrijft
deze lokaal als `hydamo.gpkg`.

## Gebruik in Waterlagen

GKW HYDAMO is invoer voor [afwateringseenheden](../bewerkte-lagen/afwateringseenheden.md)
en de gemaalklassen bij [functioneel landgebruik](../bewerkte-lagen/functioneel-landgebruik.md).
Daarvoor worden de puntlaag `gemaal`, `globalid` en `maximalecapaciteit` gebruikt.
Volgens het DAMO-objectenhandboek is de capaciteit van een gemaal uitgedrukt
in m³/minuut. De afzonderlijke laag `pomp` wordt hierbij niet opgeteld.
Een ontbrekende capaciteit is geen capaciteit van nul; de bron kan onvolledig zijn.

Voor afwateringseenheden is ook de lijnlaag `duikersifonhevel` vereist; een lege
laag is geldig. De herkomst wordt bewaard via onder meer `nen3610id`, `globalid`,
`code` en de oorspronkelijke FID. Duikers met waterbeheercode `80` worden niet
uit GKW gebruikt, ook niet wanneer de [RWS-bron](rijkswateren.md) geen duikers
bevat. Een eigen levering moet eveneens een duikerlaag bevatten en vervangt
alle duikers van de gekozen beheerder zonder terugval op GKW. Zie
[productie en bronvervanging](../produceren/afwateringseenheden.md#eigen-levering).

## Externe verwijzingen

- [GKW HYDAMO-package](https://nhipackages.blob.core.windows.net/packages/gkw-hydamo-package.zip)
- [DAMO-objectenhandboek: Gemaal, inclusief eenheid maximaleCapaciteit](https://damo.hetwaterschapshuis.nl/DAMO%202.4/Objectenhandboek%20DAMO%202.4/html/Gemaal.html)
