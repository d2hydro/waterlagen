# Afwateringseenheden produceren

Deze pagina gebruikt [scripts/afwateringseenheden_aa_en_maas.py](../../scripts/afwateringseenheden_aa_en_maas.py) als werkend
voorbeeld. Het script produceert afwateringseenheden voor het beheergebied van
Aa en Maas.

## Vooraf

Installeer Waterlagen volgens [Installatie](installatie.md) en stel eerst de
locatie voor downloads en resultaten in via [Configuratie en DataStore](configuratie.md).
De workflow gebruikt de DataStore voor AHN, HYDAMO, administratieve grenzen,
tussenresultaten en het logbestand.

Voor de LDD- en subcatchmentberekening is PCRaster nodig. Voer het voorbeeld
vanuit de repository-root uit met de daarvoor ingerichte pixi-omgeving:

```bash
pixi run --environment afwateringseenheden python scripts/afwateringseenheden_aa_en_maas.py
```

## Werkgebied en parameters

Het script selecteert Aa en Maas met waterbeheercode `38`. Pas
`WATERBEHEERCODE` aan voor een ander beheergebied. De belangrijkste instellingen
zijn `BUFFER_M`, `BURN_DEPTH_M`, `MAX_FILL_DEPTH_M`, `TILE_SIZE_M` en
`TILE_BUFFER_M`. Controleer deze waarden altijd voor het beoogde werkgebied.

## Workflow

Het script voert de volgende stappen uit:

1. Downloadt en normaliseert de waterschapsgrenzen en selecteert het
   beheergebied.
2. Downloadt de AHN-DTM voor het beheergebied, inclusief de ingestelde buffer.
3. Downloadt de landelijke HYDAMO-GeoPackage.
4. Berekent afwateringseenheden in tegels volgens [Afwateringseenheden](../bewerkingen/afwateringseenheden.md#werkwijze) en schrijft een samengevoegde
`watersysteem.gpkg` `afwateringseenheden.gpkg` naar de DataStore in de sub-map `bewerkingen\afwateringseenheden`.

Na afloop logt het script het aantal berekende, overgeslagen en als randprobleem
gemelde tegels. Vergroot `TILE_BUFFER_M` en bereken gemelde tegels opnieuw
wanneer een afwateringseenheid de buffergrens bereikt.

Voor de betekenis van de uitvoer en de beperkingen van de berekening, zie
[Afwateringseenheden](../bewerkingen/afwateringseenheden.md).
