# DEM produceren

Gebruik dezelfde [datastore](configuratie.md) en voorbereide bronnen als voor
[functioneel landgebruik](landgebruik.md). De betekenis van het resultaat staat
bij [DEM met gebouwen](../bewerkingen/dem.md).

## Starten

```powershell
pixi run dem
pixi run dem --area alkmaar
```

`--area` accepteert `nederland` (standaard) en `alkmaar`. Nederland gebruikt
het volledige nationale tegelrooster. Alkmaar gebruikt vier aangrenzende tegels
van hetzelfde rooster: bij 5 km tussen `(105000, 510000)` en `(115000, 520000)`.
Beide gebieden behouden de landgebruikresolutie en pixeluitlijning.

Uitvoer staat onder `processed_data/dem/<area>/<run-id>/`. Zonder `--run-id`
wordt een nieuwe UTC-tijdstempel gebruikt. `--output-root` vervangt alleen de
uitvoerroot van DEM; landgebruik wordt gezocht in de datastore.

## Landgebruik vinden of produceren

Voor Nederland controleert DEM de nieuwste productie onder
`processed_data/functioneel_landgebruik/nederland`, op basis van de aanmaaktijd
in `run.json`. Ontbrekende of ongeschikte uitvoer leidt tot een nieuwe nationale
landgebruikproductie. Er wordt niet automatisch een oudere productie gekozen.

Voor Alkmaar wordt eerst de nieuwste Alkmaar-productie gecontroleerd. Is die
niet bruikbaar, dan worden de vier benodigde tegels uit de nieuwste nationale
productie gecontroleerd. Zijn ook die ongeschikt, dan wordt uitsluitend
landgebruik voor Alkmaar geproduceerd onder
`processed_data/functioneel_landgebruik/alkmaar/<run-id>/`.

Automatische productie gebruikt dezelfde functie, standaardbronnen en
classificatie als `pixi run functioneel_landgebruik --area <area>`.
Voorbereide BGT en de overige landgebruikbronnen moeten dus al beschikbaar zijn.
Bestaande landgebruikproducties worden niet overschreven.

De controle omvat productiestatus, classificatie-CSV, tegelgrid, bronrasters,
gebouw-ID's en voorbereide gebouwgeometrie?n. ID-cellen moeten exact overeenkomen
met broncode 10. De buurcontext moet de gekozen gebouwzoekafstand dekken.
De controle betreft de opgeslagen producten; nieuwe externe bronversies
leiden niet automatisch tot herproductie. Een nog lopende productie of een
toegangsprobleem geeft een duidelijke fout.

Met `--landuse-run PAD` kiest u expliciet een productie. Een ongeschikte expliciete
keuze geeft een fout zonder automatische uitwijk. Ontbrekend AHN-DTM wordt naar
de gedeelde AHN-bronmap gedownload; geldige bestaande tegels worden hergebruikt.
Met `--ahn-vrt PAD` gebruikt u een eigen DTM-moza?ek dat ook de donoromgeving dekt.

## Instellingen en workers

| Optie | Standaard | Betekenis |
| --- | --- | --- |
| `--area` | `nederland` | Nederland of vier Alkmaar-tegels |
| `--workers` | `DEM_WORKERS`, anders 1 | Gelijktijdige DEM-tegels |
| `--building-initial-buffer-m` | 1 | Eerste gebouwzoekafstand |
| `--building-buffer-step-m` | 1 | Toename zonder geldige donor |
| `--building-percentile` | 75 | Percentiel bij eerste geslaagde zoekactie |
| `--building-max-search-distance-m` | 5 | Maximale gebouwzoekafstand |
| `--interpolation-max-distance-m` | 250 | AHN-interpolatieafstand; 0 schakelt vullen uit |

Stel bijvoorbeeld in `.env` in:

```dotenv
FUNCTIONEEL_LANDGEBRUIK_WORKERS=4
DEM_WORKERS=1
```

De CLI heeft voorrang. DEM's `--workers` geldt uitsluitend voor DEM-tegels;
automatische landgebruikproductie gebruikt haar eigen instelling. De pools
draaien achtereenvolgens. Het aantal workers wordt begrensd door het aantal
te verwerken tegels. Elke DEM-worker gebruikt grote rasterarrays; kies een
aantal passend bij het beschikbare geheugen.

Gebouwhoogten worden eerst per tegelbatch bepaald en centraal opgeslagen.
Een pand dat meerdere tegels raakt krijgt ??n hoogte. Workers lezen alleen
hoogten voor hun eigen tegel. VRT en COG worden daarna samengesteld.
Er is geen beperking van DEM-interpolatie tot `landgebied`.

## Controleren en hervatten

Het script vergelijkt na afloop alle pixels en grid-/schaalmetadata van de VRT's
met de COG's. Inspecteer daarnaast `nodata.gpkg` en `dem_bron.tif`.

```powershell
pixi run dem --area alkmaar --run-id mijn_proef --workers 2
pixi run dem --area alkmaar --run-id mijn_proef --resume --workers 1
```

De gekozen landgebruikproductie wordt vastgelegd in `run.json`. Hervatten kiest
geen nieuwere productie. Een door DEM gestarte, onderbroken landgebruikproductie
wordt onder dezelfde run-ID hervat. Voltooide DEM-tegels en gebouwhoogten worden
hergebruikt. Workers mogen veranderen; gewijzigde rekeninstellingen of invoer
vereisen een nieuwe run-ID. `--overwrite` herberekent alleen de DEM-uitvoer van
een compatibele run en overschrijft de landgebruikafhankelijkheid niet.

De oude optie `--prepare-landuse` blijft als verouderde Alkmaar-route beschikbaar
voor eerdere opdrachten. Gebruik voor nieuwe producties de automatische workflow.
Geef bij hervatten van oudere Alkmaar-runs expliciet `--area alkmaar` en dezelfde
oorspronkelijke invoeropties op.
