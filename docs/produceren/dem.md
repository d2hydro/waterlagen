# DEM produceren

Gebruik dezelfde [datastore](configuratie.md) en voorbereide bronnen als voor
[functioneel landgebruik](landgebruik.md). De betekenis van het resultaat staat
bij [DEM met gebouwen](../bewerkingen/dem.md).

## Starten

```powershell
pixi run dem
pixi run dem --area alkmaar
```

DEM gebruikt dezelfde [gebieden en CLI-opties](cli.md) als de andere producten.
De gebiedsgrens selecteert volledige tegelkernen; uitvoer wordt niet afgeknipt.
Alkmaar gebruikt bij een tegelgrootte van 5 km vier tegels. De landgebruikresolutie
en pixeluitlijning blijven behouden.

Uitvoer staat onder `processed_data/dem/<area>/<run-id>/`.
`--output-root` vervangt de productiemap, ook voor de automatische afhankelijkheid.

## Landgebruik vinden of produceren

DEM controleert per beschikbaar gebied de nieuwste landgebruikrun op basis van
de aanmaaktijd in `run.json`. Het gevraagde gebied krijgt voorrang. Alleen een
productie met alle benodigde tegelkernen en voldoende gebouwcontext is geschikt;
bij een ongeschikte nieuwste run wordt binnen dat gebied geen oudere gekozen.
Anders produceert DEM zelf landgebruik voor het gevraagde gebied, inclusief
ontbrekende bronvoorbereiding. Met `--refresh-sources` wordt automatisch een
nieuwe afhankelijkheid gemaakt. Expliciete bronpaden blijven expliciete keuzes.

Bestaande landgebruikproducties worden niet overschreven. De geneste productie
krijgt eigen metadata en schrijft in het `productie.log` van de DEM-run.

De controle omvat productiestatus, classificatie-CSV, tegelgrid, bronrasters,
gebouw-ID's en voorbereide gebouwgeometrieën. ID-cellen moeten exact overeenkomen
met broncode 10. De buurcontext moet de gekozen gebouwzoekafstand dekken.
De controle betreft de opgeslagen producten; nieuwe externe bronversies
leiden niet automatisch tot herproductie. Een nog lopende productie of een
toegangsprobleem geeft een duidelijke fout.

Met `--landuse-run PAD` kiest u expliciet een productie. Een ongeschikte expliciete
keuze geeft een fout zonder automatische uitwijk. Ontbrekend AHN-DTM wordt naar
de gedeelde AHN-bronmap gedownload; geldige bestaande tegels worden hergebruikt.
Een AHN-verzoek heeft standaard een verbindingstimeout en leespauzetimeout van
60 seconden. Na een timeout probeert de downloader de betreffende tegel opnieuw,
maximaal tien pogingen in totaal. Bij gebruik van de Python-functie
`download_ahn` kan de timeout met `timeout` worden ingesteld.
Met `--ahn-vrt PAD` gebruikt u een eigen DTM-mozaïek dat ook de donoromgeving dekt.

## Instellingen en workers

| Optie | Standaard | Betekenis |
| --- | --- | --- |
| `--area` | `nederland` | Nederland, Alkmaar of waterschapscode |
| `--workers` | `DEM_WORKERS`, anders 1 | Gelijktijdige DEM-tegels |
| `--building-workers` | `DEM_BUILDING_WORKERS`, anders 4 | Gelijktijdige batches voor gebouwhoogten |
| `--building-initial-buffer-m` | 1 | Eerste gebouwzoekafstand |
| `--building-buffer-step-m` | 1 | Toename zonder geldige donor |
| `--building-percentile` | 75 | Percentiel bij eerste geslaagde zoekactie |
| `--building-max-search-distance-m` | 5 | Maximale gebouwzoekafstand |
| `--interpolation-max-distance-m` | 250 | AHN-interpolatieafstand; 0 schakelt vullen uit |

Stel bijvoorbeeld in `.env` in:

```dotenv
FUNCTIONEEL_LANDGEBRUIK_WORKERS=4
DEM_WORKERS=1
DEM_BUILDING_WORKERS=4
```

De CLI heeft voorrang. DEM's `--workers` geldt uitsluitend voor DEM-tegels;
automatische landgebruikproductie gebruikt haar eigen instelling. De pools
draaien achtereenvolgens. Het aantal workers wordt begrensd door het aantal
te verwerken tegels. Elke DEM-worker gebruikt grote rasterarrays; kies een
aantal passend bij het beschikbare geheugen.

Gebouwhoogten worden eerst per tegelbatch parallel bepaald en centraal opgeslagen.
De eerste tegel die een gebouw bevat krijgt de berekening toegewezen. Andere
tegels gebruiken hetzelfde resultaat. Iedere worker leest zijn eigen AHN-bestand
en schrijft een afzonderlijk batchbestand; alleen het hoofdproces schrijft naar
de gezamenlijke hoogtetabel. Vier workers is een behoudende startwaarde;
meer workers helpen alleen als geheugen en schijf voldoende capaciteit hebben.
Een pand dat meerdere tegels raakt krijgt één hoogte. Workers lezen alleen
hoogten voor hun eigen tegel. VRT en COG worden daarna samengesteld.
Er is geen beperking van DEM-interpolatie tot `landgebied`.

## Integer- en floatuitvoer

Iedere productie schrijft zowel `dem.tif` met de bestaande AHN-opslag en
schaalmetadata als `dem_float.tif` met directe Float32-hoogten in meters.
Er is geen extra CLI-optie nodig. Houd rekening met opslag voor een tweede COG
en tijdelijke bestanden tijdens de conversie. De conversie verandert `dem.tif`
niet. Zie de [uitvoerbeschrijving](../bewerkingen/dem.md#uitvoer) voor afronding,
compressie en de gezamenlijke bronrasters.

## Controleren en hervatten

Tijdens de gebouwstap toont de console het aantal afgehandelde tegelbatches,
opgeslagen gebouwhoogten, actieve batches en verstreken tijd. Dezelfde tellers
staan in `gebouwhoogten_status.json`. Tijdens parallel rekenen volgt minimaal
elke 30 seconden een voortgangsmelding zolang het hoofdproces op workers wacht.
Daarna worden afgeronde DEM-tegels direct geteld, ook als een eerdere tegel nog
bezig is. De NoData-controle, COG-conversies en pixelcontroles hebben afzonderlijke
voortgangsbalken met de naam van de bewerking of het bestand.

Het script vergelijkt na afloop alle pixels en grid-/schaalmetadata van de VRT's
met de COG's. Ook worden alle float-pixels en hun geldigheidsmasker vergeleken
met de gedecodeerde waarden van `dem.tif`. Inspecteer daarnaast `nodata.gpkg`, `ahn_bron.tif` en `dem_bron.tif`.

De interpolatieafstand is een harde grens. Resterende NoData blokkeert de
publicatie niet, ook niet binnen `landgebied`. Het script leest `landgebied`
uit de bestuurlijke gebieden van 2026 in de ingestelde datastore.
`dem_coverage.json` rapporteert de ontbrekende cellen in het eind-DEM buiten
`landgebied`, in water en in overig landgebruik. Inspecteer daarnaast de drie
[diagnostiekcategorieen](../bewerkingen/dem.md#uitvoer) in `nodata.gpkg`.
Bestands-, grid-, CRS- en pixelcontroles blijven fouten tegenhouden.

```powershell
pixi run dem --area alkmaar --run-id mijn_proef --workers 2
pixi run dem --area alkmaar --run-id mijn_proef --resume --workers 1 --building-workers 4
```

De gekozen landgebruikproductie wordt vastgelegd in `run.json`. Hervatten kiest
geen nieuwere productie. Een door DEM gestarte, onderbroken landgebruikproductie
wordt onder dezelfde run-ID hervat. Voltooide DEM-tegels en gebouwhoogten worden
hergebruikt. Een ontbrekende of gewijzigde float-export wordt bij hervatten
opnieuw gemaakt uit het bestaande geldige `dem.tif`. Een afzonderlijk checkpoint
bewaart de afgeronde basisuitvoer, zodat een mislukte float-export geen nieuwe
tegelberekening of integer-COG vereist. De volledige productie is pas gereed
nadat ook `dem_float.tif` is gevalideerd. Workers mogen veranderen; gewijzigde rekeninstellingen of invoer
vereisen een nieuwe run-ID. `--overwrite` herberekent alleen de DEM-uitvoer van
een compatibele run en overschrijft de landgebruikafhankelijkheid niet.

De dekkingscontrole registreert haar bron en beleid afzonderlijk in
`dem_coverage_inputs.json`. Een eerdere run die op de oude, strengere controle
van alle tegelkernen stopte, kan daardoor dezelfde tegels en gebouwhoogten
hergebruiken. Er wordt opnieuw gecontroleerd voordat eindbestanden verschijnen.
Een latere wijziging van de vastgelegde landsgrens vereist een nieuwe run-ID.

Bij hervatten wordt verouderde NoData-diagnostiek afzonderlijk vernieuwd, zonder
gebouwhoogten of interpolatie opnieuw te berekenen. Per tegel registreert
`diagnostics.json` de diagnostiekversie. Zowel de tegelbestanden `nodata.gpkg`
als het landelijke bestand krijgen de kolom `categorie`. Gebruik voor een run
die eerder op resterende NoData stopte dezelfde run-ID met `--resume`.

Voltooide gebouwbatches blijven in `gebouwhoogten_batches/` bewaard. Bij een
onderbreking blijft ook `gebouwhoogten.tmp.gpkg` behouden. Hervatten herstelt
voltooide batches en berekent alleen ontbrekende gebouwen, mits invoer en
rekeninstellingen overeenkomen. Beide aantallen workers mogen daarbij veranderen.

Een nog lopende run van oudere code kan de tijdelijke hoogtetabel bij stoppen
verwijderen. Maak voor zo'n overstap eerst een consistente kopie met de SQLite
backup-API als `gebouwhoogten.resume.gpkg` in dezelfde runmap. Kopieer een actief
GeoPackage niet rechtstreeks met een bestandenkopie. Als de tijdelijke tabel
ontbreekt, neemt de nieuwe workflow deze backup over bij hervatten.

Nieuwe productie gebruikt tegelmappen volgens de
[uitvoerstructuur](../bewerkingen/dem.md#uitvoer). Gebruik een nieuwe run-ID
voor deze structuur en het gewijzigde NoData-beleid; eerdere DEM-runs worden
niet automatisch gemigreerd. Geldige landgebruikinputs met de oude platte
tegelstructuur blijven leesbaar, inclusief hun bron- en gebouwbestanden.
Nederland en Alkmaar gebruiken dezelfde automatische workflow. De oude
Alkmaar-proefroute met `--prepare-landuse` is verwijderd; proefruns zonder
`workflow_version` kunnen niet meer worden hervat. Start daarvoor een nieuwe
productie met `--area alkmaar`.


## Tijdelijk vergrendelde uitvoerbestanden

DEM gebruikt dezelfde begrensde herhaalpogingen voor bestandsvervanging en
hetzelfde herstel van gevalideerde tijdelijke COG's als landgebruik.
Zie [tijdelijk vergrendelde uitvoerbestanden](landgebruik.md#tijdelijk-vergrendelde-uitvoerbestanden).
