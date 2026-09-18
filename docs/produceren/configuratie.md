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
