# Afwateringseenheden produceren

Deze pagina gebruikt [scripts/afwateringseenheden_aa_en_maas.py](https://github.com/d2hydro/waterlagen/blob/main/scripts/afwateringseenheden_aa_en_maas.py) als werkend
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

| Instelling | Eenheid | Betekenis en effect |
|---|---|---|
| `WATERBEHEERCODE` | — | Selecteert het waterschap; `"38"` is Aa en Maas. |
| `BUFFER_M` | meter | Extra strook buiten de waterschapsgrens waarin ook afwateringseenheden worden berekend. |
| `TILE_SIZE_M` | meter | Zijde van iedere rekentegel, zonder tegelbuffer. Grotere tegels vragen doorgaans meer geheugen. |
| `TILE_BUFFER_M` | meter | Extra terrein rondom iedere rekentegel dat wordt meegenomen in de berekening. Een grotere buffer kan randproblemen verminderen, maar kost extra rekentijd en geheugen. |
| `BURN_DEPTH_M` | meter | Verlaging van secundaire waterlopen in het hoogtemodel; primaire waterlopen worden tweemaal zo diep ingebrand. |
| `MAX_FILL_DEPTH_M` | meter | Maximale diepte van depressies die bij het berekenen van de afstroomrichting worden opgevuld. |

`BUFFER_M = 5000` vergroot het werkgebied én de uitvoer met 5 km buiten de
waterschapsgrens. `TILE_BUFFER_M` is extra rekenterrein rondom elke tegel;
alleen het resultaat binnen de tegelkern wordt opgenomen.

## Workflow

Het script voert de volgende stappen uit:

1. Download en normaliseert de waterschapsgrenzen en selecteert het
   beheergebied.
2. Download de AHN-DTM voor het beheergebied, inclusief de ingestelde buffer.
3. Download de landelijke HYDAMO-GeoPackage.
4. Berekent afwateringseenheden in tegels volgens [Afwateringseenheden](../bewerkingen/afwateringseenheden.md#werkwijze) en schrijft
   `watersysteem.gpkg` en de samengevoegde `afwateringseenheden.gpkg` naar de DataStore in de submap `bewerkingen\afwateringseenheden`.

Na afloop logt het script het aantal berekende, overgeslagen en als randprobleem
gemelde tegels. Vergroot `TILE_BUFFER_M` en bereken gemelde tegels opnieuw
wanneer een afwateringseenheid de buffergrens bereikt.

Voor de betekenis van de uitvoer en de beperkingen van de berekening, zie
[Afwateringseenheden](../bewerkingen/afwateringseenheden.md).
