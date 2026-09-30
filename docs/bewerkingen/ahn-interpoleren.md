# AHN interpoleren

## Doel

Deze bewerking vult gaten in gedownloade AHN-rastertegels zodat een bruikbaarder
hoogteraster ontstaat.

## Bronnen

- [AHN](../bronnen/ahn.md)

## Werkwijze

Waterlagen leest een VRT of verzameling AHN-tegels, vult NoData-gebieden binnen
de tegels tot de opgegeven maximale zoekafstand en schrijft een nieuwe set
GeoTIFFs. Optioneel wordt daar opnieuw een VRT voor gemaakt.

De zoekafstand wordt opgegeven in meters en omgerekend naar rasterpixels.
De lokale inverse-afstandsinterpolatie verandert uitsluitend ontbrekende
waarden; oorspronkelijke geldige AHN-cellen blijven behouden. Een doelmasker
kan bepalen welke gaten mogen worden gevuld, onafhankelijk van de donors.
Bij [DEM met gebouwen](dem.md) geldt geen beperking tot `landgebied`.

## Uitvoer

De uitvoer is een map met ingevulde GeoTIFFs of een VRT die naar deze tegels
verwijst. De rastereigenschappen volgen de aangeleverde brontegels.

## Aandachtspunten en beperkingen

De maximale zoekafstand bepaalt welke gaten worden overbrugd. NoData buiten
de bronextents wordt niet door de brondekking opgelost.

## Zelf produceren

Gebruik in een eigen Python-workflow `get_ahn_rasters` om AHN op te halen en
daarna `interpolate_ahn_tiles` om gaten te vullen; zie de [AHN-API](../reference/ahn.md).
