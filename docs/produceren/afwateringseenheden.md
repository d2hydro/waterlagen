# Afwateringseenheden produceren

Met het meegeleverde script `scripts/afwateringseenheden.py` produceert
u afwateringseenheden voor een waterschap. Zonder extra opties
verwerkt het script Aa en Maas. U kiest een ander waterschap met de
waterbeheercode in de opdracht; u hoeft het script niet aan te passen.

## Vooraf

Volg [Installatie](installatie.md) om het productiepakket te downloaden,
uit te pakken en met Pixi te installeren. De meegeleverde `.datastore` bewaart
gegevens standaard onder `./data`. Zie [Opslag van gegevens](configuratie.md)
als u een andere locatie wilt gebruiken.
De workflow gebruikt de DataStore voor AHN, HYDAMO, administratieve grenzen,
tussenresultaten en het logbestand.

Voor de LDD- en subcatchmentberekening is PCRaster nodig. Dit zit in de
Pixi-omgeving van het productiepakket. Controleer die vanuit uw projectfolder:

```console
pixi run --locked controleer
```

`./data` is de submap `data` in uw Waterlagen-projectfolder. Controleer of daar
voldoende vrije schijfruimte is: deze workflow download AHN-tegels en landelijke
bronnen en schrijft rasters en tussenresultaten. Het is een volledige productie,
geen kleine installatietest. De benodigde ruimte en rekentijd hangen af van het
werkgebied.

## Starten

Start na de melding `Imports en rastercontrole OK` de productie voor Aa en Maas.
Voer deze opdracht uit in PowerShell vanuit uw projectfolder:

```console
pixi run --locked afwateringseenheden
```

Deze Pixi-taak voert `./scripts/afwateringseenheden.py` uit.
U kunt het script ook starten met
`pixi run --locked python ./scripts/afwateringseenheden.py`.

Laat PowerShell open tijdens het rekenen. De voortgang verschijnt in PowerShell
en in het logbestand. Met `Ctrl+C` kunt u onderbreken. Een volgende start
hergebruikt geldige bronbestanden, maar maakt een nieuwe uitvoermap en hervat
de berekeningen uit de vorige uitvoermap niet.

## Een waterschap kiezen

Geef na `--waterbeheercode` de code van het gewenste waterschap op. Voor
Aa en Maas is dat `38`:

```powershell
pixi run --locked afwateringseenheden --waterbeheercode 38
```

Eerst controleert het script de opgegeven code aan de hand van de
waterschapsgrenzen. Een onbekende code stopt de opdracht voordat AHN- en
HYDAMO-gegevens voor de productie worden opgehaald.

## Rekenen op een pc met minder werkgeheugen

Met `--workers` bepaalt u hoeveel rekentegels parallel worden berekend. Gebruik
bijvoorbeeld maximaal twee werkprocessen voor Aa en Maas:

```powershell
pixi run --locked afwateringseenheden --waterbeheercode 38 --workers 2
```

Er werken maximaal twee processen tegelijk aan rekentegels. Gebruik `--workers 1`
als uw pc weinig werkgeheugen heeft: de tegels worden dan één voor één verwerkt.
Dat vraagt minder geheugen voor gelijktijdige berekeningen, maar kan langer duren.

Geef een geheel getal vanaf `1` op. Zonder `--workers` gebruikt het script de
bestaande instelling voor het aantal werkprocessen, standaard `4`.
De waterbeheercode en het opgegeven aantal werkprocessen gelden voor deze
opdracht. U hoeft daarvoor `pixi.toml`, `pixi.lock` of het script niet aan te passen.
Voor hulp bij het gebruik voert u uit:

```powershell
pixi run --locked afwateringseenheden --help
```

## Vaste rekeninstellingen

Via de opdracht kiest u het werkgebied en het aantal werkprocessen. De overige
rekeninstellingen liggen vast in het meegeleverde script en horen bij de
productiemethode. Onderstaande waarden lichten de berekening toe. Laat deze
waarden bij het uitvoeren van de productie ongewijzigd.

| Instelling | Vaste waarde | Betekenis |
|---|---|---|
| Gebiedsbuffer | 2000 m | Extra strook buiten de waterschapsgrens waarvoor ook afwateringseenheden worden berekend. |
| Tegelgrootte | 10 × 10 km | Grootte van iedere tegelkern, zonder tegelbuffer. |
| Tegelbuffer | 2000 m | Extra rekenterrein rondom iedere tegel; alleen het resultaat binnen de tegelkern wordt opgenomen. |
| Inbranddiepte | 100 m | Verlaging van secundaire waterlopen in het hoogtemodel; primaire waterlopen worden tweemaal zo diep ingebrand. |
| Maximale opvuldiepte | 50 m | Maximale diepte van depressies die bij het berekenen van de afstroomrichting worden opgevuld. |
| PCRaster-seed | 12345 | Vaste startwaarde per tegel voor de berekening. |

De rasterresolutie is 2 m. Door de gebiedsbuffer kunnen de resultaten van
aangrenzende waterschappen elkaar overlappen. Zie
[Afwateringseenheden](../bewerkingen/afwateringseenheden.md) voor de
productiemethode en de interpretatie van de uitkomsten.

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

Elke productie krijgt een nieuwe uitvoermap. Bij de standaardopslag staat deze
onder `./data` in uw projectfolder:

```text
data/processed_data/afwateringseenheden/waterschap_<code>_<datum-tijd>/
```

Voor Aa en Maas begint de mapnaam met `waterschap_38_`. De datum en tijd
onderscheiden de producties; eerdere resultaten blijven behouden.

### Bestanden in de uitvoermap

| Bestand of map | Inhoud |
|---|---|
| `afwateringseenheden.gpkg` | De berekende afwateringseenheden; open dit bestand in QGIS. |
| `watersysteem.gpkg` | Het watersysteem dat voor de berekening is voorbereid. |
| `tiles.gpkg` | De geselecteerde tegelkernen, met voor elke tegel een `tile_id`. |
| `afwateringseenheden.log` | Het hoofdlog met voortgang, verwerkingstijden en gemelde randproblemen. |
| `tiles/<tegel-id>/` | Rasters en polygonen per rekentegel. De mapnaam komt overeen met `tile_id` in `tiles.gpkg`. |

### Logbestanden en verwerkingstijd

De verwerkingstijd per tegel staat in `afwateringseenheden.log`. Bij parallel
rekenen staat deze ook in `tiles/<tegel-id>/workflow.log`.

Het log vermeldt ook wanneer achtergebleven NoData-cellen worden aangevuld.

Voor hergebruik in een eigen workflow en de bijbehorende cachevoorwaarden,
zie de [API-referentie](../reference/afwateringseenheden.md#dekking-en-hergebruik).

Voor de betekenis van de uitvoer en de beperkingen van de berekening, zie
[Afwateringseenheden](../bewerkingen/afwateringseenheden.md).

## Eigen Python-workflow

Gebruik het meegeleverde script als vertrekpunt. De functies voor de
tegelberekening staan in de [API-referentie](../reference/afwateringseenheden.md).
