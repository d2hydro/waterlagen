---
editorial_status: ai
---

# Bewerkte lagen samenstellen met Python

Gebruik deze voorbeelden om zelf bronnen, instellingen en bewerkingen te
combineren. Elk script toont de stappen met publieke functies onder de
productie-API. Volg eerst [Aan de slag](gebruik.md) voor installatie en uitvoering.

Stel bovenaan het script `DATA_DIR`, `AREA` en `EXPERIMENT` in.
Downloads worden hergebruikt. Een eigen bestand gebruiken kan door de
downloadaanroep te vervangen door het betreffende pad; laag- en veldnamen
moeten aansluiten op de [API-referentie](api.md).
Tussenresultaten blijven beschikbaar om te bekijken of verder te bewerken.

De uitvoer staat onder
`data/processed_data/voorbeelden/alkmaar_centrum/<experiment>/`.
Kies bij andere bronnen of instellingen een nieuwe experimentnaam. Losse
functies kunnen eerder gemaakte bestanden hergebruiken zonder de gewijzigde
instellingen toe te passen. Dit is geen automatisch beheerde productierun.

Landelijke bronbestanden blijven groot, ook voor Alkmaar-centrum.
Bij de rastervoorbeelden zijn de instellingen onderdeel van de methode:
een andere buffer, resolutie of indeling kan andere resultaten geven dan de
[standaardproductie](../produceren/cli.md).

## Afwateringseenheden

Lees de HYDAMO-objecten, selecteer primaire en secundaire watergangen en
bereid de segmenten voor met `prepare_watersysteem`. Daarna berekent
`calculate_afwateringseenheden_tiles` de afwateringseenheden.

Instelbaar zijn onder meer de verbindingstolerantie, segmentlengte,
tegelgrootte, buffer, rasterresolutie en inbranddiepte.
Het voorbeeld gebruikt een kerntegel van 1 km met 2 km buffer; het
samengevoegde resultaat wordt op Alkmaar-centrum geknipt. AHN en watersysteem
worden ook voor de omgeving opgehaald. HYDAMO blijft een landelijke download.
Gebruik de omgeving met PCRaster.

Uitvoer: `watersysteem.gpkg`, tegelbestanden en `afwateringseenheden.gpkg`.
Bekijk ook de gemelde randproblemen en resterende gaten in het resultaat.

[Betekenis van de laag](../bewerkte-lagen/afwateringseenheden.md) ·
[API-referentie](afwateringseenheden.md)

[Download het Python-script](voorbeelden/produceer_afwateringseenheden.py).

```python
--8<-- "docs/reference/voorbeelden/produceer_afwateringseenheden.py"
```

## Auto's

Haal BAG en CBS op en koppel de woon-VBO's aan buurten met `bouw_vbo_buurt`.
Die voorbereiding is landelijk en wordt ook door het inwonersvoorbeeld gebruikt.
`HERBOUW_VOORBEREIDING=True` vernieuwt de koppeling na een bronwijziging;
het downloadt geen nieuwe bronversies.

Selecteer daarna de complete buurten die Alkmaar-centrum overlappen en behoud
alle bijbehorende woon-VBO's, ook buiten het vierkant. Geef die GeoDataFrames
aan `bereken_personenautos_per_vbo`. Het resultaat kan direct worden bekeken,
met andere gegevens worden gecombineerd of worden opgeslagen in `autos.gpkg`.
Verklein de VBO-selectie pas na de berekening; anders ontbreekt buurtcontext.

[Betekenis van de laag](../bewerkte-lagen/autos.md) ·
[API-referentie](autos.md) · [Gedeelde voorbereiding](vbo_buurt.md)

[Download het Python-script](voorbeelden/produceer_autos.py).

```python
--8<-- "docs/reference/voorbeelden/produceer_autos.py"
```

## Hoogtemodel

Voer eerst het landgebruikvoorbeeld uit. Kies met `LANDUSE_EXPERIMENT`
welke uitsnede als invoer dient. Het bronraster, de gebouw-ID's en de
voorbereide pandgeometrieën moeten bij die uitsnede blijven.

Stel met `DemConfig` de interpolatieafstand, gebouwzoekafstanden en het
percentiel in. De maximale gebouwzoekafstand mag niet groter zijn dan de
`BUILDING_CONTEXT_M` waarmee het landgebruik is voorbereid.
`bouw_dem_tiles` berekent het DEM op hetzelfde rasterrooster. Het originele
AHN en het landgebruik moeten dezelfde resolutie en pixeluitlijning hebben;
er wordt niet automatisch herschaald.

Het voorbeeld haalt AHN op voor de uitsnede én de omgeving van volledige panden.
Vervang het VRT-pad in de bouwstap om eigen AHN-invoer te gebruiken.
Uitvoer: `dem/dem.tif`, de floatversie, bronrasters en controlebestanden.

[Betekenis van de laag](../bewerkte-lagen/dem.md) · [API-referentie](dem.md)

[Download het Python-script](voorbeelden/produceer_dem.py).

```python
--8<-- "docs/reference/voorbeelden/produceer_dem.py"
```

## Functioneel landgebruik

De downloadstappen tonen alle gebruikte bronnen. Daarna worden LIWO-vlakken
en een index van BAG-panden voorbereid. Met `FunctioneelLandgebruikSources`
kiest u expliciet de invoer voor `bouw_functioneel_landgebruik`.

Pas de resolutie, aanvulafstand of classificatietabel aan. Het voorbeeld maakt
een rechthoek van 1 × 1 km; bij 0,5 m zijn dat 4 miljoen rastercellen, plus
tijdelijke rekenruimte. De downloads en een deel van de bronvoorbereiding
blijven landelijk. De BGT-download bevat hier de zes benodigde objecttypen;
het kleine BGT-downloadvoorbeeld met alleen panden en water is hiervoor onvoldoende.

De pandindex en `BUILDING_CONTEXT_M` zorgen dat het resultaat ook voor het DEM
kan worden gebruikt. Houd dan de resolutie op 0,5 m. Met `landgebied_path`
wordt de landsgrens voor het aanvullen expliciet meegegeven.

Uitvoer: `functioneel_landgebruik/functioneel_landgebruik.tif`, met bronraster,
gebouwgegevens, QGIS-stijl en controlebestand. Dit is een losse rasteruitsnede.

[Betekenis van de laag](../bewerkte-lagen/functioneel-landgebruik.md) ·
[API-referentie](functioneel_landgebruik.md)

[Download het Python-script](voorbeelden/produceer_functioneel_landgebruik.py).

```python
--8<-- "docs/reference/voorbeelden/produceer_functioneel_landgebruik.py"
```

## Inwoners

Dit voorbeeld gebruikt dezelfde landelijke BAG/CBS-koppeling en selectie
van complete buurten als [Auto's](#autos).
Met `bereken_inwoners_per_vbo` worden beide verdeelmethoden berekend.
De uitkomst is een GeoDataFrame: bekijk de kolommen, voeg eigen analyses toe
en kies zelf wat u opslaat. Het voorbeeld schrijft `inwoners.gpkg`.

[Betekenis van de laag](../bewerkte-lagen/inwoners.md) ·
[API-referentie](inwoners.md) · [Gedeelde voorbereiding](vbo_buurt.md)

[Download het Python-script](voorbeelden/produceer_inwoners.py).

```python
--8<-- "docs/reference/voorbeelden/produceer_inwoners.py"
```

