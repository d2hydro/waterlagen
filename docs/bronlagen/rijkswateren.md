---
editorial_status: ai
---

# Rijkswateren

## Beschrijving

Deze bron bevat voorbereide hydroobjectlijnen voor Rijkswaterstaat, met
waterbeheercode `80` in `nen3610id`. De bron wordt handmatig gepubliceerd.
Het is geen automatische download van een officiële Rijkswaterstaatregistratie.

## Leverancier

De distributie staat op de waterlagen-cloud van d2hydro. De voorbereidende
repository beschrijft de bronproductie; deze keten wordt hier niet uitgevoerd.
Controleer bronversie, dekking en gebruiksvoorwaarden vóór inhoudelijke publicatie.

## Dataset of service

De openbare cloud-URL verwijst naar een Nextcloud-share. Daarin staat
`hydamo/rws_hydamo.gpkg`, met laag `hydroobject`. De downloader volgt de redirect
en haalt het afzonderlijke bestand op. De sharetoken wordt niet vast ingesteld.
De bronlocatie kan worden aangepast en een geldige lokale bron wordt zonder
netwerkverkeer hergebruikt.

Bij controle op 15 oktober 2026 bevatte de distributie 2.305 LineStrings in
`EPSG:28992`, met `categorieoppervlaktewater = primair`. Aanwezige attributen
waren `globalid`, `nen3610id`, `categorieoppervlaktewater`, `naam`, `bron`,
`osm_id` en `osm_laag`. Dit beschrijft één bronversie en bewijst geen volledige
of hydrologisch gevalideerde landelijke dekking. Kunstwerklagen zijn niet vereist.

## Gebruik in Waterlagen

De bron levert de Rijkswaterstaat-hydroobjecten voor
[afwateringseenheden](../bewerkte-lagen/afwateringseenheden.md).
Zie de [productie-instructies](../produceren/afwateringseenheden.md) voor
doelselectie, brandcontext, bronvervanging en controle-uitvoer.

## Externe verwijzingen

- [Openbare waterlagen-cloud](https://waterlagen.d2hydro.nl)
- [Voorbereidende bronproductie](https://github.com/d2hydro/rws_hydroobject)

Beide verwijzingen zijn op 15 oktober 2026 gecontroleerd.
