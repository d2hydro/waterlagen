---
editorial_status: ai
---

# BGT

## Beschrijving

De Basisregistratie Grootschalige Topografie (BGT) beschrijft grootschalige
topografische objecten, waaronder wegen, waterdelen en panden.

## Leverancier

Kadaster, ontsloten via PDOK.

## Dataset of service

Waterlagen gebruikt de PDOK BGT Download API. Daarin kan een landelijke,
vooraf samengestelde GML-light-download of een aanvraag voor geselecteerde
featuretypen en een gebied worden gebruikt.

## Gebruik in Waterlagen

BGT wordt gebruik als bron bij:
- [functioneel landgebruik](../bewerkte-lagen/functioneel-landgebruik.md); BGT-wegdelen beschrijven hier deze functie
- [afwateringseenheden](../bewerkte-lagen/afwateringseenheden.md). BGT-duikers worden gebruikt bij het maken van de signaalkaart. Optioneel kunnen BGT lagen (waterdelen, wegen, duikers, ...) gebruikt worden als brandlagen.

## Externe verwijzingen

- [BGT Download API](https://api.pdok.nl/lv/bgt/download/v1_0/ui/)
- [Landelijke BGT GML-light-download](https://api.pdok.nl/lv/bgt/download/v1_0/full/predefined/bgt-gmllight-nl-nopbp.zip)
