# Afwateringseenheden produceren

Deze productie ondersteunt Nederland, een waterschapscode en gedeelde gebieden
zoals Alkmaar. Volg eerst [Installatie](installatie.md); het releasepakket bevat
PCRaster. Vanuit de repository gebruikt u de omgeving `afwateringseenheden`.

## Starten

```console
pixi run --locked afwateringseenheden --area alkmaar --workers 2
pixi run --locked afwateringseenheden --waterbeheercode 38 --workers 2
```

Zonder gebiedsoptie wordt **Nederland** verwerkt. Een onbekende waterschapscode
geeft een fout voordat AHN en HYDAMO worden opgehaald. Kies `--workers 1` bij
weinig werkgeheugen. De overige [gedeelde CLI-opties](cli.md) regelen opslag,
bronvernieuwing, offline gebruik en hervatten.

## Workflow

1. Het gebied selecteert volledige tegelkernen van 10 x 10 km.
2. De productie haalt de benodigde AHN-tegels, bestuurlijke gebieden en HYDAMO
   op, of hergebruikt lokale bronnen. De AHN-selectie dekt ook de tegelbuffers.
3. HYDAMO-objecten worden ruimtelijk geselecteerd met de benodigde context.
   De beheerder van een object vormt geen extra filter.
4. De productie berekent de tegels en voegt de bruikbare resultaten samen.
   De gebiedsgrens knipt het resultaat niet af.

De tegelbuffer is 2000 m, de rasterresolutie 2 m, de inbranddiepte voor
secundaire waterlopen 100 m en de maximale opvuldiepte 50 m. De vaste seed is
12345. De landsgrens begrenst de AHN-interpolatie tot Nederland. Dit staat los
van de gekozen gebiedsgrens als invoerselectie.
De betekenis en beperkingen staan bij
[Afwateringseenheden](../bewerkingen/afwateringseenheden.md).

## Uitvoer en hervatten

Elke run staat onder `processed_data/afwateringseenheden/<gebied>/<run-id>/`.

| Bestand | Inhoud |
| --- | --- |
| `afwateringseenheden.gpkg` | Samengestelde afwateringseenheden. |
| `watersysteem.gpkg` | Voorbereid watersysteem voor alle geselecteerde tegels. |
| `input/ahn.vrt` | Gebiedsspecifieke verwijzingen naar gedeelde AHN-tegels. |
| `tiles/tiles.gpkg` | Geselecteerde tegelkernen. |
| `tiles/<tegel-id>/` | Rasters, polygonen en status per rekentegel. |
| `productie.log` | Hoofdlog, inclusief de werkprocessen. |
| `run.json` | Instellingen, bronidentiteit, pakketversie en runstatus. |

```console
pixi run --locked afwateringseenheden --area alkmaar --run-id proef
pixi run --locked afwateringseenheden --area alkmaar --run-id proef --resume
```

Fouten in afzonderlijke tegels verhinderen het samenvoegen, terwijl overige
onafhankelijke tegels worden afgewerkt. Hervatten hergebruikt geldige resultaten.
Zie [productiemappen](configuratie.md#productiemappen) voor de compatibiliteitsvoorwaarden.

Gebruik voor eigen code de [Python-ingang](../reference/gebruik.md) of de
[lagere API](../reference/afwateringseenheden.md#dekking-en-hergebruik).
