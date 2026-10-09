# Gedeelde productiecommando's

Waterlagen heeft vijf productie-ingangen: `autos`, `inwoners`,
`afwateringseenheden`, `functioneel_landgebruik` en `dem`.
Elke ingang haalt ontbrekende bronnen op en bereidt ze voor. Bestaande bronnen
worden hergebruikt. Ook voor een klein gebied kunnen landelijke bronnen nodig zijn.

Daarnaast controleert `pixi run controleer` de installatie, imports en
rasterbibliotheken zonder brongegevens te downloaden.

```console
pixi run autos --area alkmaar --run-id proef
pixi run inwoners --area 38 --run-id proef
pixi run functioneel_landgebruik --area alkmaar --workers 2
pixi run dem --area alkmaar --workers 1
pixi run afwateringseenheden --area nederland --workers 2
```

In het releasepakket gebruikt u `pixi run --locked`. Vanuit de repository vereist
afwateringseenheden de omgeving met PCRaster:
`pixi run --environment afwateringseenheden afwateringseenheden --area alkmaar`.
Elk commando heeft `--help`. Rechtstreeks starten met
`pixi run python scripts/autos.py` geeft dezelfde CLI.

## Gebieden

Alle producten accepteren `--area nederland` (standaard), `--area alkmaar` of
een waterschapscode, bijvoorbeeld `--area 38` of `--area waterschap_38`.
`--waterbeheercode 38` is een alternatieve schrijfwijze; combineer deze niet met
`--area`. Eén opdracht verwerkt één gebied.

De gebiedsgrens selecteert de invoer. De uitvoer wordt **niet op die grens
geknipt**: volledige tegelkernen, objecten en noodzakelijke rekencontext blijven
behouden. Daardoor kan uitvoer buiten het gekozen gebied liggen.
Inwoners en auto's gebruiken volledige intersecterende CBS-buurten met alle
bijbehorende woon-VBO's. Afwateringseenheden selecteert objecten ruimtelijk,
zonder extra filter op de waterbeheerder van een object.

Alkmaar is een vaste Polygon in `waterlagen.areas`, in EPSG:28992 met begrenzing
`(105000, 510000, 115000, 520000)`. De polygon verandert niet met de tegelgrootte.
Aanvullende vaste gebieden worden in diezelfde module opgenomen en getest.

## Opties

| Optie | Gedrag |
| --- | --- |
| `--area GEBIED` | Gedeelde invoerselectie; standaard Nederland. |
| `--data-dir PAD` | Bronmap en productiemap onder `PAD/source_data` en `PAD/processed_data`. |
| `--output-root PAD` | Productiemap, ook voor automatisch geproduceerde afhankelijkheden. |
| `--run-id NAAM` | Eigen runnaam; standaard een UTC-tijdstempel. |
| `--resume` | Hervat de expliciet benoemde, compatibele run. |
| `--overwrite` | Bereken de uitvoer van die compatibele run opnieuw. |
| `--refresh-sources` | Vernieuw bronnen voor een nieuwe run; bouw afhankelijke broncaches opnieuw op wanneer de invoer wijzigt. |
| `--offline` | Gebruik lokale bronnen; ontbrekende bronnen geven een fout zonder download. |
| `--debug` | Neem diagnostische meldingen op in het productielog. |
| `--workers AANTAL` | Werkprocessen voor landgebruik, DEM en afwateringseenheden. |

`--refresh-sources` kan niet samen met `--resume`, `--overwrite` of `--offline`.
Bronnen vernieuwen en uitvoer overschrijven zijn dus afzonderlijke handelingen.
De opties van de opdracht hebben voorrang op `.datastore`, `.env` en
omgevingsvariabelen. Er is geen aanvullende configuratiefile nodig.
Zie [Opslag van gegevens](configuratie.md) voor bronpaden en runcompatibiliteit.

## Voortgang, fouten en hervatten

Elke CLI schrijft `productie.log` in de hoofdproductiemap. Hierin staan ook de
voorbereiding, berichten van werkprocessen en automatisch gestarte producties.
De terminal toont hoofdvoortgang en fouten. Er worden tijdens deze productie
geen afzonderlijke workerlogs aangemaakt. Statusbestanden en `run.json` blijven
bij de betreffende producten staan.

Een DEM-run kan landgebruik nodig hebben. Die productie krijgt een eigen runmap
en metadata, deelt de bronnen en schrijft in hetzelfde hoofdlog. De gekozen
landgebruikrun wordt vastgelegd voor hervatten.

Na een tegelfout worden de overige onafhankelijke tegels afgewerkt. Een
onvolledige productie publiceert geen nieuw samengesteld eindproduct en eindigt
met een foutstatus. Geldige tussenresultaten blijven beschikbaar voor `--resume`.
Een bestaande uitvoer van een eerdere berekening kan nog aanwezig zijn; beoordeel
ook de status in `run.json`.

## Migratie van eerdere scripts

| Eerdere ingang | Huidige ingang |
| --- | --- |
| `auto.py` / taak `auto` | `autos.py` / taak `autos` |
| Taak `landgebruik` | Taak `functioneel_landgebruik` |
| Losse downloadscripts, waaronder `bag.py`, `brp.py` en `top10nl.py` | Automatische bronvoorbereiding of de bestaande Python-downloadfuncties. |
| `bgt_actuele_vlakken.py`, `liwo_overstromingsgevoelige_gebieden.py` | Automatische landgebruikvoorbereiding; losse bewerking via Python. |
| `controle_bag_landgebruik.py`, `controle_gemalen_landgebruik.py` | `waterlagen.functioneel_landgebruik.controle` en `controle_gemalen`. |
| `statistiek_inwoners_autos.py` | `waterlagen.vbo_buurt.statistiek`. |
| `controleer_productie.py` | `pixi run controleer` blijft beschikbaar en roept de omgevingscontrole in de package aan. Zie [Installatie](installatie.md). |
| Benchmarks en profilers onder `scripts/` | Ontwikkelgereedschap onder `tools/`. |

Er zijn geen oude taakaliassen meer. Bestaande bronbestanden blijven bruikbaar.
Runmetadata van een eerdere architectuur wordt niet automatisch gemigreerd;
start bij gewijzigde instellingen of gebiedsidentiteit een nieuwe run.
Voor gebruik in eigen code staan er [Python-voorbeelden](../reference/gebruik.md).
