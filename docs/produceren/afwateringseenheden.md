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

### Parallel rekenen

Het script gebruikt momenteel kernen van 10 × 10 km, een tegelbuffer van 2 km,
een resolutie van 2 m en seed 12345 per tegel. Het aantal processen volgt
`settings.afwateringseenheden_workers`, standaard 4. Stel dit in via `.env`:

```dotenv
AFWATERINGSEENHEDEN_WORKERS=4
```

Meer workers vragen meer werkgeheugen. De workers rekenen in afzonderlijke
processen; het hoofdproces voegt de resultaten samen. Het script begrenst de
native rekenthreads per worker op één. Start het vanuit een terminal; voor
eigen parallelle scripts is een `if __name__ == "__main__"`-guard nodig.

## Workflow

Het script voert de volgende stappen uit:

1. Downloadt en normaliseert de waterschapsgrenzen en selecteert het
   beheergebied.
2. Controleert de AHN-selectie inclusief gebiedsbuffer, hergebruikt geldige
   tegels en downloadt ontbrekende tegels.
3. Downloadt [bestuurlijke gebieden](../bronnen/bestuurlijke-gebieden.md),
   standaard jaargang 2026, of hergebruikt de bestaande bron. De laag
   `landgebied` begrenst de DEM-interpolatie tot Nederland, inclusief tegelbuffers.
4. Hergebruikt of downloadt de landelijke HYDAMO-GeoPackage en bereidt het
   watersysteem voor het huidige werkgebied opnieuw voor.
5. Berekent afwateringseenheden in tegels volgens
   [Afwateringseenheden](../bewerkingen/afwateringseenheden.md#werkwijze) en voegt
   de resultaten samen. Randproblemen leiden niet tot automatisch herberekenen
   met een grotere buffer; gaten worden waar mogelijk aangevuld vanuit buurtegels.

Na afloop logt het script het aantal berekende, overgeslagen en als randprobleem
gemelde tegels. De randproblemen betreffen de situatie vóór het aanvullen.

## Uitvoermap en logging

Elke start maakt een nieuwe map
`<datastore.afwateringseenheden_path>/aa_en_maas_<datum-tijd>/` met
`watersysteem.gpkg`, `afwateringseenheden.gpkg`, `afwateringseenheden.log` en
`tiles.gpkg`. Deze GeoPackage bevat de geselecteerde kerntiles; de waarde in
`tile_id` is gelijk aan de naam van de bijbehorende map
`tiles/<tegel-id>/`. Elke tegelmap bevat rasters, tegelpolygonen en
`workflow.log`.
Eerdere runs blijven behouden. De standaard hoofdmap is
`data/processed_data/afwateringseenheden`.

De verwerkingstijd per tegel staat in het hoofdlog en, bij parallel rekenen,
in `tiles/<tegel-id>/workflow.log`. Deze tijd omvat rastervoorbereiding,
afwatering en uitvoer; wachttijd in de pool en gezamenlijk samenvoegen vallen
erbuiten. Bij hergebruik meet de timer alleen het controleren en verwerken
van de bestaande tegeluitvoer. Het vangnet voor achtergebleven NoData-cellen
wordt eveneens gelogd.

Voor hergebruik in een eigen workflow en de bijbehorende cachevoorwaarden,
zie de [API-referentie](../reference/afwateringseenheden.md#dekking-en-hergebruik).

Voor de betekenis van de uitvoer en de beperkingen van de berekening, zie
[Afwateringseenheden](../bewerkingen/afwateringseenheden.md).
