---
editorial_status: ai
---

# Bronlagen downloaden met Python

Elk voorbeeld is een zelfstandig script. Volg eerst [Aan de slag](gebruik.md)
voor installatie, de opslagmap en het uitvoeren van een script.
Instellingen staan bovenaan: pas de gegevensmap en het hergebruik aan, en
bij AHN/BGT ook het gebied, de AHN-versie of de objecttypen.
Bestaande bestanden worden zoveel mogelijk hergebruikt. Voor een nieuwe bronversie
kan bewust opnieuw downloaden nodig zijn; zie het cachegedrag in de API-referentie.

Waar een download ruimtelijk kan worden beperkt, gebruiken de voorbeelden
**Alkmaar-centrum**. Landelijke bestanden worden volledig opgehaald:
een klein voorbeeldgebied maakt die downloads niet kleiner.
Een volledige productie haalt de benodigde bronnen zelf op; het is niet nodig
alle onderstaande scripts eerst uit te voeren.

## Rijkswateren

De volledige handmatig gepubliceerde GeoPackage is ook voor kleine gebieden nodig.
Het voorbeeld hergebruikt een geldige lokale bron zonder netwerkverkeer.

[Over deze bron](../bronlagen/rijkswateren.md) · [API-referentie](rijkswateren.md)

```python
--8<-- "docs/reference/voorbeelden/download_rijkswateren.py"
```

[Download het script](voorbeelden/download_rijkswateren.py).

## AHN

Download de AHN4-DTM-tegels die Alkmaar-centrum raken, met resolutie 0,5 m. Hele AHN-tegels worden opgehaald; de download is groter dan het voorbeeldgebied. Het resultaat is een VRT met bijbehorende GeoTIFFs.

[Over deze bron](../bronlagen/ahn.md) · [API-referentie](ahn.md)

[Download het Python-script](voorbeelden/download_ahn.py).

```python
--8<-- "docs/reference/voorbeelden/download_ahn.py"
```

## BAG

Download de landelijke BAG-light als GeoPackage. Dit is een groot bestand; de download wordt niet beperkt tot Alkmaar-centrum. De productievoorbeelden gebruiken deze bron voor panden en woon-VBO's.

[Over deze bron](../bronlagen/bag.md) · [API-referentie](bag.md)

[Download het Python-script](voorbeelden/download_bag.py).

```python
--8<-- "docs/reference/voorbeelden/download_bag.py"
```

## Bestuurlijke gebieden

Download het landelijke GeoPackage met bestuurlijke gebieden voor het standaardjaar. Het bestand bevat onder meer de landsgrens die de rasterproducties gebruiken. De gebiedsselectie volgt pas bij het verwerken.

[Over deze bron](../bronlagen/bestuurlijke-gebieden.md) · [API-referentie](administratieve_gebieden.md)

[Download het Python-script](voorbeelden/download_bestuurlijke_gebieden.py).

```python
--8<-- "docs/reference/voorbeelden/download_bestuurlijke_gebieden.py"
```

## BGT

Vraag voor Alkmaar-centrum de objecttypen waterdeel en pand op. Het resultaat bestaat uit afzonderlijke GeoPackages in een eigen map. Dit is een klein voorbeeld van een BGT-aanvraag; de volledige landgebruikproductie gebruikt een landelijk BGT-bestand met meer objecttypen. Dit voorbeeld vervangt die bron niet.

[Over deze bron](../bronlagen/bgt.md) · [API-referentie](bgt.md)

[Download het Python-script](voorbeelden/download_bgt.py).

```python
--8<-- "docs/reference/voorbeelden/download_bgt.py"
```

## BRP

Zoek de nieuwste definitieve BRP-release en download het landelijke GeoPackage. Dit kan een groot bestand zijn. Een bestaand doelbestand wordt hergebruikt; de releasefeed wordt wel geraadpleegd.

[Over deze bron](../bronlagen/brp.md) · [API-referentie](brp.md)

[Download het Python-script](voorbeelden/download_brp.py).

```python
--8<-- "docs/reference/voorbeelden/download_brp.py"
```

## CBS

Download de landelijke Wijk- en Buurtkaart 2025 als GeoPackage en de benodigde kerncijfers als JSON. Ook voor Alkmaar-centrum zijn dit landelijke bronnen. De producties voor inwoners en auto's selecteren later volledige CBS-buurten.

[Over deze bron](../bronlagen/cbs.md) · [API-referentie](cbs.md)

[Download het Python-script](voorbeelden/download_cbs.py).

```python
--8<-- "docs/reference/voorbeelden/download_cbs.py"
```

## Dijkringen

Download de landelijke historische dijkringen als GeoPackage. Deze bron is niet tot Alkmaar-centrum beperkt. Zie de bronpagina voor het peiljaar en de interpretatie.

[Over deze bron](../bronlagen/dijkringen.md) · [API-referentie](dijkringen.md)

[Download het Python-script](voorbeelden/download_dijkringen.py).

```python
--8<-- "docs/reference/voorbeelden/download_dijkringen.py"
```

## GKW HYDAMO

Download het landelijke HYDAMO-archief en haal het GeoPackage daaruit. Het archief kan groot zijn. De selectie van het watersysteem rond Alkmaar-centrum gebeurt in de afwateringseenhedenproductie.

[Over deze bron](../bronlagen/hydamo.md) · [API-referentie](hydamo.md)

[Download het Python-script](voorbeelden/download_hydamo.py).

```python
--8<-- "docs/reference/voorbeelden/download_hydamo.py"
```

## LIWO

Download het landelijke raster met overstromingsgevoelige gebieden als GeoTIFF. Deze functie haalt de volledige dekking op, ook wanneer later alleen Alkmaar-centrum wordt verwerkt.

[Over deze bron](../bronlagen/liwo.md) · [API-referentie](liwo.md)

[Download het Python-script](voorbeelden/download_liwo.py).

```python
--8<-- "docs/reference/voorbeelden/download_liwo.py"
```

## OSM-drinkwaterlocaties

Haal de geometrieën van de beoordeelde drinkwaterlocaties uit OSM op en schrijf ze naar een GeoPackage. Dit is de landelijke selectie van beoordeelde locaties, geen volledige OSM-download en geen selectie rond Alkmaar-centrum.

[Over deze bron](../bronlagen/osm-drinkwater.md) · [API-referentie](osm_drinkwater.md)

[Download het Python-script](voorbeelden/download_osm_drinkwater.py).

```python
--8<-- "docs/reference/voorbeelden/download_osm_drinkwater.py"
```

## TOP10NL

Download het landelijke TOP10NL-GeoPackage. Dit is een grote download die niet door het voorbeeldgebied wordt begrensd.

[Over deze bron](../bronlagen/top10nl.md) · [API-referentie](top10nl.md)

[Download het Python-script](voorbeelden/download_top10nl.py).

```python
--8<-- "docs/reference/voorbeelden/download_top10nl.py"
```

## Waterketen DAMO

Download de landelijke Waterketen DAMO als GeoPackage. De bron blijft landelijk; de ruimtelijke selectie volgt bij het verwerken.

[Over deze bron](../bronlagen/waterketen-damo.md) · [API-referentie](waterketen_damo.md)

[Download het Python-script](voorbeelden/download_waterketen_damo.py).

```python
--8<-- "docs/reference/voorbeelden/download_waterketen_damo.py"
```

## Waterschapsgrenzen

Download het GeoPackage met alle waterschapsgrenzen. Voor het vaste voorbeeldgebied Alkmaar-centrum is geen waterschapsgrens nodig; dit voorbeeld laat zien hoe deze bron afzonderlijk wordt opgehaald.

[Over deze bron](../bronlagen/waterschapsgrenzen.md) · [API-referentie](administratieve_gebieden.md)

[Download het Python-script](voorbeelden/download_waterschapsgrenzen.py).

```python
--8<-- "docs/reference/voorbeelden/download_waterschapsgrenzen.py"
```

