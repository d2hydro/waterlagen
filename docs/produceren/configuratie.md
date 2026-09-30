# Opslag van gegevens

## Beginnen zonder instellingen

**U hoeft niets in te stellen.** Het productiepakket bevat al een bestand
`.datastore` met `DATA_DIR=./data`. Daardoor maakt Waterlagen automatisch een
map `data` aan in uw projectfolder

- `data/source_data`: gedownloade brongegevens;
- `data/processed_data`: verwerkte resultaten.

Open PowerShell in uw projectfolder,
waar `pixi.toml` en `pixi.lock` staan.
Controleer de installatie en de gebruikte gegevensmap met:

```powershell
pixi run --locked controleer
```

Kies daarna een productie bij [Zelf produceren](index.md).

## Productiemappen

De huidige productiescripts voor `autos`, `inwoners`, `afwateringseenheden` en
`functioneel_landgebruik` gebruiken één conventie:

```text
processed_data/<dataset>/<werkgebied>/<run-id>/
```

| Dataset | Werkgebied | Voorbeeld van een resultaat |
| --- | --- | --- |
| `autos` | `nederland` | `autos/nederland/20260925T120000Z/autos.gpkg` |
| `inwoners` | `nederland` | `inwoners/nederland/20260925T120000Z/inwoners.gpkg` |
| `afwateringseenheden` | `waterschap_<code>` | `afwateringseenheden/waterschap_38/20260925T120000Z/afwateringseenheden.gpkg` |
| `functioneel_landgebruik` | `nederland` | `functioneel_landgebruik/nederland/20260925T120000Z/functioneel_landgebruik.tif` |

Zonder opties maakt iedere opdracht een nieuwe run met een UTC-tijdstempel
`YYYYMMDDTHHMMSSZ`. Die tijd duidt de productie aan, niet het peiljaar van de
bron. Meerdere waterschappen binnen één opdracht krijgen dezelfde run-ID,
elk onder hun eigen werkgebied. Een naamconflict geeft een foutmelding;
een bestaande map wordt nooit stilzwijgend hergebruikt.

Alle vier de scripts accepteren dezelfde opties:

| Optie | Gedrag |
| --- | --- |
| `--run-id NAAM` | Maak een nieuwe run met een eigen naam, bijvoorbeeld `20260925T120000Z_alternatieve_mapping`. |
| `--run-id NAAM --resume` | Hervat die bestaande run en hergebruik aanwezige resultaten waar de workflow dat ondersteunt. |
| `--run-id NAAM --overwrite` | Bereken de uitvoer in die bestaande run opnieuw, met dezelfde instellingen en bronnen. |

Gebruik voor een naam 1–100 letters, cijfers, underscores of koppeltekens,
beginnend met een letter of cijfer; geef geen pad op. `--resume` en `--overwrite`
vereisen een expliciete run-ID en kunnen niet samen worden gebruikt.

Bijvoorbeeld, vanuit de repositoryhoofdmap:

```console
pixi run python scripts/functioneel_landgebruik.py --run-id proef
pixi run python scripts/functioneel_landgebruik.py --run-id proef --resume
pixi run python scripts/functioneel_landgebruik.py --run-id proef --overwrite
```

De uitvoermap wordt bij aanvang gelogd. Productielogs en `run.json` staan bij
de resultaten. `run.json` registreert de geïnstalleerde pakketversie,
rekeninstellingen, bronpaden, bronidentiteit en de status `running`, `complete`
of `failed`. Landgebruik bewaart daarnaast de CSV en registreert zijn SHA-256.
Herstarten met andere instellingen, een andere pakketversie, gewijzigde
bronbestanden of een andere mapping vereist een **nieuwe run-ID**, ook met
`--overwrite`. Het aantal workers mag bij hervatten wel veranderen.

Voor grote bronbestanden vergelijkt de controle pad, grootte en wijzigingstijd;
het is geen volledige inhoudscontrole. Lokale VRT's worden op inhoud en hun
bronverwijzingen gecontroleerd. Codewijzigingen binnen dezelfde pakketversie
worden niet automatisch herkend: kies daarvoor zelf een nieuwe run-ID.
Een achtergebleven `.run.lock` mag alleen worden verwijderd als er geen
productie meer actief is.

Downloads en gedeelde tussenproducten, zoals `processed_data/vbo_buurt`, blijven
op hun bestaande locaties en worden niet per run gekopieerd. De runcontrole
registreert die bestanden, maar vervangt hun eigen cachevoorwaarden niet.
Vernieuw verouderde tussenproducten dus afzonderlijk voordat u een nieuwe
productie start.

Bestaande uitvoermappen worden niet verplaatst of automatisch als nieuwe run
overgenomen. De Python-pakketfuncties en vaste `DataStore`-paden blijven
beschikbaar voor bestaande workflows. Geef in vervolganalyses expliciet de
resultaten van de gewenste run op; er wordt geen automatische “laatste run”
gekozen. Deze conventie geldt voor de huidige scripts; oudere gedownloade
productiepakketten kunnen nog de eerdere mapindeling gebruiken.

## Gegevens ergens anders bewaren

Wilt u bijvoorbeeld een andere schijf gebruiken omdat daar meer ruimte is?
Dan kunt u de opslaglocatie opgeven in **`.datastore`**. Dat is een gewoon
tekstbestand met instellingen, geen map en geen Python-script.
De naam begint met een punt en heeft geen `.txt` erachter.

1. Open uw projectfolder in VS Code.
2. Open het meegeleverde bestand **`.datastore`**, direct naast
   `pixi.toml` en `pixi.lock`.
3. De instelling voor de standaardmap ziet er zo uit:

    ```text
    DATA_DIR=./data
    ```

   `./data` verwijst naar `data` in uw projectfolder.
   Wilt u gegevens ergens anders bewaren, vervang dan `./data` door het
   volledige pad naar de gewenste opslagmap. Laat `DATA_DIR=` staan.

4. Sla het bestand op als **UTF-8 zonder BOM** (in VS Code heet dit `UTF-8`).
5. Start uw script opnieuw vanuit uw projectfolder.

Met `DATA_DIR=./data` blijft de opslaglocatie `<projectfolder>/data`.
Bij een ander pad komen `source_data` en
`processed_data` onder die gekozen opslagmap. Uw Pixi-bestanden, `.datastore`
en scripts blijven in uw projectfolder staan:

```text
<projectfolder>/
├── pixi.toml
├── pixi.lock
├── .datastore              # meegeleverd: bevat de gekozen opslaglocatie
└── scripts/
    └── afwateringseenheden.py
```

U hoeft `.datastore` niet zelf te openen of uit te voeren bij elke start.
Waterlagen leest het automatisch uit de map van waaruit u de opdracht uitvoert.
Zet het daarom in uw projectfolder, boven de submap `scripts`.

**Bestaande gegevens worden niet automatisch verplaatst.** Als u een andere
opslaglocatie kiest, blijven eerdere downloads op hun oude plek staan.
Gebruik steeds dezelfde opslaglocatie om downloads te hergebruiken.

??? info "Meer instellingen en technische details"
    Met `SOURCE_DATA_DIR` en `PROCESSED_DATA_DIR` kunt u brongegevens en
    resultaten afzonderlijke opslaglocaties geven. Omgevingsvariabelen met
    dezelfde namen hebben voorrang op de instellingen in `.datastore`.

    Neem geen `.env` over uit een ontwikkelomgeving met nieuwere workflows.
    Voor de meegeleverde producties hoeft u geen `.env` te maken. Bij
    [afwateringseenheden](afwateringseenheden.md) stelt u het aantal
    werkprocessen zo nodig in met `--workers`.

    In de Python-code heet het onderdeel dat de opslaglocaties beheert
    `DataStore`. De [API-referentie](../reference/datastore.md) beschrijft de
    huidige broncode en kan nieuwer zijn dan uw gedownloade release.
