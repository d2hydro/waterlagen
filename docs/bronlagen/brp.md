---
editorial_status: ai
---

# BRP

## Beschrijving

De Basisregistratie Gewaspercelen (BRP) bevat de ligging van landbouwpercelen
en het daarbij geregistreerde gewas. Per jaar wordt een dataset met peildatum
15 mei gemaakt.

<span id="leverancier"></span>

## Herkomst

De Rijksdienst voor Ondernemend Nederland (RVO) beheert de perceelregistratie. Gebruikers van landbouwpercelen geven jaarlijks hun percelen en gewassen op. De landelijke selectie is beschikbaar via PDOK.

## Dataset of service

Waterlagen leest de PDOK Atom-feed en kiest daaruit de meest recente definitieve
GeoPackage-release. Voorlopige, concept- en testreleases worden overgeslagen.

## Gebruik in Waterlagen

BRP-gewaspercelen zijn invoer voor [functioneel landgebruik](../bewerkte-lagen/functioneel-landgebruik.md).

## Externe verwijzingen

- [BRP op PDOK](https://www.pdok.nl/introductie/-/article/basisregistratie-gewaspercelen-brp-)
- [BRP Atom-feed](https://service.pdok.nl/rvo/gewaspercelen/atom/basisregistratie_gewaspercelen_brp.xml)
