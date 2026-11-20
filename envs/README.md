# Waterlagen @VERSION@ produceren

Dit pakket hoort bij release **@TAG@**. Het installeert Waterlagen **@VERSION@**
uit PyPI en bevat de bijbehorende openbare productiescripts. Een Git-checkout of
toegang tot een private repository is niet nodig.

Installeer [Pixi](https://pixi.prefix.dev/latest/installation/) en pak de ZIP uit
in een map naar keuze. De bestanden staan direct
in de ZIP, zonder extra bovenliggende map. De gekozen map met `pixi.toml`,
`pixi.lock` en `scripts` is uw **projectfolder**.

Open de projectmap in Windows Verkenner. Typ `cmd` (opdrachtprompt) of `powershell` in de adresbalk en druk op Enter. Open op Linux een terminal in de projectmap. Voer beide opdrachten één voor één uit:

```text
pixi install --locked
pixi run --locked controleer
```

De controle toont de Waterlagen-versie, importeert de scripts en test een klein
raster met GDAL, Rasterio en PCRaster. Er worden geen brongegevens gedownload.

## Een productie starten

1. Dubbelklik op Windows in de projectmap op `run-maken.bat`. De Run Maker opent in uw browser.
2. Kies het gebied en de kaartlagen die u wilt maken. Bij **Extra opties** ziet u de instellingen voor de gekozen kaartlaag. De Run Maker zet uw keuzes om in een runscript.
3. Kies **Opslaan en starten** om de berekening direct uit te voeren. Met **Alleen opslaan** bewaart u het script voor later. Dubbelklik dan op het opgeslagen `.bat`-bestand om de berekening te starten.

Voor Linux of geautomatiseerde runs kunt u de [Pixi-productiecommando’s](https://d2hydro.github.io/waterlagen/produceren/cli/) gebruiken.

## Bronnen en resultaten

De productie hergebruikt beschikbare bronnen en haalt ontbrekende gegevens op. Ook voor een klein gebied kan een landelijke download nodig zijn. Het gebied bepaalt welke invoer wordt gebruikt. De resultaten kunnen buiten die grens vallen.

Elke runmap bevat `productie.log` en `run.json`. Controleer de resultaten voordat u ze gebruikt.

De meegeleverde `.datastore` bevat `DATA_DIR=./data`. Daardoor staan downloads en
resultaten onder `data` in uw projectfolder. Pas alleen deze instelling aan als
u een andere opslaglocatie wilt. Bewaar ook dit bestand bij het verplaatsen van
de projectfolder. Start opdrachten vanuit de map met `pixi.toml`.

Bewaar `pixi.toml` en `pixi.lock` samen en gebruik `--locked`: het lockbestand legt
de dependencyversies voor Windows en Linux vast. Internet is nodig voor de eerste
installatie en voor het downloaden van brongegevens.

## Code bijwerken

Werk tussen producties bij naar een nieuwe release van Waterlagen. Hervat onderbroken runs eerst met de oorspronkelijke versie.

- **Windows:** dubbelklik op `code_bijwerken.bat`.
- **Linux:** voer `sh ./code_bijwerken.sh` uit.

Bevestig de update. Uw instellingen en gegevens blijven behouden.

Heeft uw oude installatie nog `bijwerken.cmd` of `bijwerken.sh`? Gebruik eenmalig
de [startopdracht voor bestaande installaties](https://d2hydro.github.io/waterlagen/produceren/installatie/#bijwerken-bestaande-installatie).
Die haalt de losse updater van de release op en werkt dezelfde projectmap bij.
Daarna gebruikt u de gewone starters hierboven. Vervang de oude updaterbestanden
niet handmatig: de update controleert hun oorspronkelijke inhoud voordat zij
binnen de normale back-up- en herstelprocedure worden vervangen.
