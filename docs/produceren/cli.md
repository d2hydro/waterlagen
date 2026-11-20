---
editorial_status: ai
---

# Via de terminal produceren

Open een terminal in de uitgepakte projectmap. Kies één opdracht. Deze voorbeelden gebruiken Alkmaar-centrum; zonder gebiedsoptie is Nederland de standaard.

```console
pixi run --locked afwateringseenheden --area alkmaar_centrum
pixi run --locked functioneel_landgebruik --area alkmaar_centrum
pixi run --locked dem --area alkmaar_centrum
pixi run --locked inwoners --area alkmaar_centrum
pixi run --locked autos --area alkmaar_centrum
```

Voeg `--help` toe voor de opties van een kaartlaag.

## Gebieden

Gebruik bijvoorbeeld `--area nederland`, `--waterbeheercode 38` (Aa en Maas) of een eigen rechthoek. De selectie omvat volledige tegelkernen of CBS-buurten. Ook een klein gebied kan landelijke bronbestanden vereisen.

??? info "Omvang van de voorbeeldgebieden"

    | Product | `alkmaar` | `alkmaar_centrum` |
    | --- | --- | --- |
    | Functioneel landgebruik en DEM | 4 tegels van 5 × 5 km | 1 tegel van 5 × 5 km |
    | Afwateringseenheden | 2 tegels van 10 × 10 km | 1 tegel van 10 × 10 km |

    De buffers komen daar nog bij. Eén landgebruik-/DEM-tegel bevat bij 0,5 m
    resolutie al 100 miljoen cellen. Deze selectie verkleint dus de gebiedsbewerking,
    maar is geen garantie voor een snelle proefrun of kleine downloads. Landelijke
    bronbestanden blijven nodig. Bij inwoners en auto's gebeurt ook de gedeelde
    voorbereiding van BAG en CBS landelijk; daarna worden de volledige CBS-buurten
    geselecteerd die het voorbeeldgebied raken.

### Eigen rechthoekig gebied

`--bounds xmin ymin xmax ymax` selecteert overlappende tegels of buurten in het project-CRS (standaard RD, EPSG:28992). Gebruik een punt voor decimalen.

## Opties

??? info "Gedeelde opdrachtregelopties"

    | Optie | Gedrag |
    | --- | --- |
    | `--area GEBIED` | Kies Nederland, een vast voorbeeldgebied of een waterschap. Standaard Nederland. |
    | `--waterbeheercode CODE` | Kies een waterschap, bijvoorbeeld `--waterbeheercode 38` voor Aa en Maas. |
    | `--bounds XMIN YMIN XMAX YMAX` | Kies een eigen rechthoek in het project-CRS. |
    | `--data-dir PAD` | Bronmap en productiemap onder `PAD/source_data` en `PAD/processed_data`. |
    | `--output-root PAD` | Productiemap, ook voor automatisch geproduceerde afhankelijkheden. |
    | `--run-id NAAM` | Eigen runnaam; standaard een UTC-tijdstempel. |
    | `--resume` | Hervat de expliciet benoemde, compatibele run. |
    | `--overwrite` | Bereken de uitvoer van die compatibele run opnieuw. |
    | `--refresh-sources` | Vernieuw bronnen voor een nieuwe run; bouw afhankelijke broncaches opnieuw op wanneer de invoer wijzigt. |
    | `--offline` | Gebruik lokale bronnen; ontbrekende bronnen geven een fout zonder download. |
    | `--debug` | Neem diagnostische meldingen op in het productielog. |
    | `--workers AANTAL` | Maximaal aantal tegels dat tegelijk wordt berekend bij landgebruik, DEM en afwateringseenheden. Met `--workers 2` worden maximaal twee tegels parallel berekend; met `--workers 1` één tegel tegelijk. |
    | `--help` | Toon de beschikbare opties voor het gekozen commando. |

    `--refresh-sources` kan niet samen met `--resume`, `--overwrite` of `--offline`.
    Bronnen vernieuwen en uitvoer overschrijven zijn dus afzonderlijke handelingen.
    De opties van de opdracht hebben voorrang op `.datastore`, `.env` en
    omgevingsvariabelen. Er is geen aanvullende configuratiefile nodig.
    Zie [Opslag van gegevens](configuratie.md) voor bronpaden en runcompatibiliteit.

## Voortgang, fouten en hervatten

Bekijk `productie.log` bij een fout. Controleer `run.json` voor de eindstatus. Met `--run-id NAAM --resume` hervat u een compatibele run. Met `--run-id NAAM --overwrite` berekent u de uitvoer opnieuw. [Opslag en runmappen](configuratie.md#productiemappen)

<span id="migratie-van-eerdere-scripts"></span>

??? info "Oudere scripts en hun huidige naam"

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
