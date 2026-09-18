# Afwateringseenheden produceren

!!! warning "Vereist nieuwere broncode"
    Deze workflow is niet beschikbaar in release 2026.2.1 of de bijbehorende
    productie-TOML. De instructies hieronder horen bij de broncoderepository
    `waterlagen`. Gebruik de [ontwikkelomgeving](../bijdragen/ontwikkelomgeving.md)
    met de omgeving `afwateringseenheden`.

Met het meegeleverde script `scripts/afwateringseenheden_aa_en_maas.py` produceert
u afwateringseenheden voor het hele beheergebied van Aa en Maas. Voor uitvoering
met de standaardinstellingen hoeft u het script niet aan te passen.

## Vooraf

Installeer vanuit de broncodemap de benodigde omgeving:

```console
pixi install --environment afwateringseenheden --locked
```

Stel de locatie voor downloads en resultaten in met `.datastore`, zoals
beschreven bij [Configuratie en DataStore](configuratie.md).
De workflow gebruikt de DataStore voor AHN, HYDAMO, administratieve grenzen,
tussenresultaten en het logbestand.

Voor de LDD- en subcatchmentberekening is PCRaster nodig. Dit zit in de
Pixi-omgeving `afwateringseenheden`. Controleer die vanuit de broncodemap:

```console
pixi run --environment afwateringseenheden python -c "from osgeo import gdal, gdal_array; import rasterio, pcraster; print('Imports OK')"
```

`./data` is de submap `data` in uw Waterlagen-projectmap. Controleer of daar
voldoende vrije schijfruimte is: deze workflow download AHN-tegels en landelijke
bronnen en schrijft rasters en tussenresultaten. Het is een volledige productie,
geen kleine installatietest. De benodigde ruimte en rekentijd hangen af van het
werkgebied en de instellingen.

## Starten

Start na de melding `Imports OK` de productie:

```console
pixi run --environment afwateringseenheden python scripts/afwateringseenheden_aa_en_maas.py
```

Laat de terminal open tijdens het rekenen. De voortgang verschijnt in de terminal
en in het logbestand. Met `Ctrl+C` kunt u onderbreken. Een volgende start
hergebruikt geldige bronbestanden, maar maakt een nieuwe uitvoermap en hervat
de berekeningen uit de vorige uitvoermap niet.

## Werkgebied en parameters

Het script selecteert Aa en Maas met waterbeheercode `38`. De instellingen staan
bovenin het script. Pas `WATERBEHEERCODE` aan voor een ander beheergebied en
controleer de overige instellingen voor dat gebied.

| Instelling | Standaard | Betekenis en effect |
|---|---|---|
| `WATERBEHEERCODE` | `"38"` | Waterbeheercode; `38` is Aa en Maas. |
| `BUFFER_M` | `2000` | Extra strook in meters buiten de waterschapsgrens waarin ook afwateringseenheden worden berekend. |
| `TILE_SIZE_M` | `10000` | Zijde in meters van iedere rekentegel, zonder tegelbuffer. Grotere tegels vragen doorgaans meer geheugen. |
| `TILE_BUFFER_M` | `2000` | Extra terrein in meters rondom iedere rekentegel. Een grotere buffer kan randproblemen verminderen, maar kost extra rekentijd en geheugen. |
| `BURN_DEPTH_M` | `100` | Verlaging in meters van secundaire waterlopen in het hoogtemodel; primaire waterlopen worden tweemaal zo diep ingebrand. |
| `MAX_FILL_DEPTH_M` | `50` | Maximale diepte in meters van depressies die bij het berekenen van de afstroomrichting worden opgevuld. |
| `RANDOM_SEED` | `12345` | Vaste PCRaster-seed per tegel. |

`BUFFER_M = 5000` vergroot het werkgebied én de uitvoer met 5 km buiten de
waterschapsgrens. `TILE_BUFFER_M` is extra rekenterrein rondom elke tegel;
alleen het resultaat binnen de tegelkern wordt opgenomen.

### Parallel rekenen

De productie gebruikt standaard kernen van 10 × 10 km, een tegelbuffer van 2 km,
een resolutie van 2 m en seed 12345 per tegel. Het aantal processen volgt
`settings.afwateringseenheden_workers`, standaard 4. Stel dit in via `.env`:

```dotenv
AFWATERINGSEENHEDEN_WORKERS=4
```

Meer workers vragen meer werkgeheugen. De workers rekenen in afzonderlijke
processen; het hoofdproces voegt de resultaten samen. De productie begrenst de
native rekenthreads per worker op één. Start het vanuit een terminal; voor
eigen parallelle scripts is een `if __name__ == "__main__"`-guard nodig.

## Workflow

De opdracht voert de volgende stappen uit:

1. Download en normaliseert de waterschapsgrenzen en selecteert het
   beheergebied.
2. Controleert de AHN-selectie inclusief gebiedsbuffer, hergebruikt geldige
   tegels en download ontbrekende tegels.
3. Download [bestuurlijke gebieden](../bronnen/bestuurlijke-gebieden.md),
   standaard jaargang 2026, of hergebruikt de bestaande bron. De laag
   `landgebied` begrenst de DEM-interpolatie tot Nederland, inclusief tegelbuffers.
4. Hergebruikt of download de landelijke HYDAMO-GeoPackage en bereidt het
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
De mapnaam begint ook bij een aangepaste waterbeheercode met `aa_en_maas_`.
Eerdere runs blijven behouden. Bij de voorbeeldopdracht is de hoofdmap
`data/processed_data/afwateringseenheden` onder de Waterlagen-projectmap.

Bij succesvolle afronding verschijnt `Aa en Maas klaar:` met onder andere
het uitvoerpad. Open `afwateringseenheden.gpkg` in QGIS en controleer
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

Gebruik het meegeleverde script als vertrekpunt. De functies voor de
tegelberekening staan in de [API-referentie](../reference/afwateringseenheden.md).
