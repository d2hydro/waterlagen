# Afwateringseenheden produceren

Met de opdracht `waterlagen afwateringseenheden` produceert u afwateringseenheden
voor een waterschap. Het voorbeeld gebruikt het hele beheergebied van Aa en Maas.
U hoeft geen Python-script aan te passen.

## Vooraf

Installeer Waterlagen volgens [Installatie](installatie.md) en stel eerst de
locatie voor downloads en resultaten in via [Configuratie en DataStore](configuratie.md).
De workflow gebruikt de DataStore voor AHN, HYDAMO, administratieve grenzen,
tussenresultaten en het logbestand.

Voor de LDD- en subcatchmentberekening is PCRaster nodig. Activeer de geïnstalleerde
omgeving en controleer die eerst:

```console
conda activate waterlagen
waterlagen controleer --data-dir D:/Waterlagen/data
```

Vervang `D:/Waterlagen/data` door uw eigen opslaglocatie. Controleer of daar
voldoende vrije schijfruimte is: deze workflow downloadt AHN-tegels en landelijke
bronnen en schrijft rasters en tussenresultaten. Het is een volledige productie,
geen kleine installatietest. De benodigde ruimte en rekentijd hangen af van het
werkgebied en de instellingen.

## Starten

Start na de melding `Installatie OK` de productie:

```console
waterlagen afwateringseenheden --waterschap 38 --data-dir D:/Waterlagen/data --workers 2
```

Laat de terminal open tijdens het rekenen. De voortgang verschijnt in de terminal
en in het logbestand. Met `Ctrl+C` kunt u onderbreken. Een volgende start
hergebruikt geldige bronbestanden, maar maakt een nieuwe uitvoermap en hervat
de berekeningen uit de vorige uitvoermap niet.

Vanuit een checkout gebruikt u in plaats daarvan:

```console
pixi run --environment afwateringseenheden waterlagen afwateringseenheden --waterschap 38 --data-dir D:/Waterlagen/data --workers 2
```

## Werkgebied en parameters

De opdracht selecteert Aa en Maas met waterbeheercode `38`. Gebruik
`--waterschap` met een andere code voor een ander beheergebied. Controleer de
instellingen altijd voor het beoogde werkgebied. Alle opties staan in:

```console
waterlagen afwateringseenheden --help
```

| Optie | Standaard | Betekenis en effect |
|---|---|---|
| `--waterschap` | `38` | Waterbeheercode; `38` is Aa en Maas. |
| `--buffer-m` | `2000` | Extra strook in meters buiten de waterschapsgrens waarin ook afwateringseenheden worden berekend. |
| `--tile-size-m` | `10000` | Zijde in meters van iedere rekentegel, zonder tegelbuffer. Grotere tegels vragen doorgaans meer geheugen. |
| `--tile-buffer-m` | `2000` | Extra terrein in meters rondom iedere rekentegel. Een grotere buffer kan randproblemen verminderen, maar kost extra rekentijd en geheugen. |
| `--burn-depth-m` | `100` | Verlaging in meters van secundaire waterlopen in het hoogtemodel; primaire waterlopen worden tweemaal zo diep ingebrand. |
| `--max-fill-depth-m` | `50` | Maximale diepte in meters van depressies die bij het berekenen van de afstroomrichting worden opgevuld. |
| `--seed` | `12345` | Vaste PCRaster-seed per tegel. |
| `--workers` | uit configuratie, anders `4` | Aantal gelijktijdige processen. |

`--buffer-m 5000` vergroot het werkgebied én de uitvoer met 5 km buiten de
waterschapsgrens. `--tile-buffer-m` is extra rekenterrein rondom elke tegel;
alleen het resultaat binnen de tegelkern wordt opgenomen.

### Parallel rekenen

De productie gebruikt standaard kernen van 10 × 10 km, een tegelbuffer van 2 km,
een resolutie van 2 m en seed 12345 per tegel. Zonder `--workers` volgt het aantal
processen `settings.afwateringseenheden_workers`, standaard 4. Stel dit in via `.env`:

```dotenv
AFWATERINGSEENHEDEN_WORKERS=4
```

Meer workers vragen meer werkgeheugen. De workers rekenen in afzonderlijke
processen; het hoofdproces voegt de resultaten samen. De productie begrenst de
native rekenthreads per worker op één. Start het vanuit een terminal; voor
eigen parallelle scripts is een `if __name__ == "__main__"`-guard nodig.

## Workflow

De opdracht voert de volgende stappen uit:

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

Na afloop logt de opdracht het aantal berekende, overgeslagen en als randprobleem
gemelde tegels. De randproblemen betreffen de situatie vóór het aanvullen.

## Uitvoermap en logging

Elke start maakt een nieuwe map
`<datastore.afwateringseenheden_path>/aa_en_maas_<datum-tijd>/` met
`watersysteem.gpkg`, `afwateringseenheden.gpkg`, `afwateringseenheden.log` en
`tiles.gpkg`. Deze GeoPackage bevat de geselecteerde kerntiles; de waarde in
`tile_id` is gelijk aan de naam van de bijbehorende map
`tiles/<tegel-id>/`. Elke tegelmap bevat rasters, tegelpolygonen en
`workflow.log`.
Voor andere waterschappen begint de mapnaam met `waterschap_<code>_`.
Eerdere runs blijven behouden. Bij de voorbeeldopdracht is de hoofdmap
`D:/Waterlagen/data/processed_data/afwateringseenheden`.

Bij succesvolle afronding verschijnt `Gereed. Open dit bestand in QGIS:` met
het pad naar `afwateringseenheden.gpkg`. Open dat bestand in QGIS en controleer
de dekking van het werkgebied en de gemelde randproblemen. Een geslaagde
berekening vervangt de inhoudelijke beoordeling van de uitkomst niet.

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

## Eigen Python-workflow

Dezelfde productie is beschikbaar via `ProductionConfig` en
`produce_afwateringseenheden` in de
[API-referentie](../reference/afwateringseenheden.md#productie-voor-een-waterschap).
Het bestaande script `scripts/afwateringseenheden_aa_en_maas.py` blijft vanuit
de repository uitvoerbaar en gebruikt de standaardinstellingen.
