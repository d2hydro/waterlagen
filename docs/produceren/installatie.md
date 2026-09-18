# Installatie

Met **Pixi** installeert en start u Waterlagen vanuit de projectmap. Pixi regelt
Python en de benodigde GIS-bibliotheken, waaronder GDAL en PCRaster. Voor het
produceren van afwateringseenheden hoeft u geen Python-code te schrijven.
De projectomgeving ondersteunt Windows en Linux; de voorbeelden hieronder
gebruiken Windows PowerShell.

## 1. Installeer Pixi

Open de [installatiepagina van Pixi](https://pixi.prefix.dev/latest/installation/)
en kies op Windows de **Windows Installer**. Voer de installer uit en open daarna
een nieuwe PowerShell-terminal. Werkt u in VS Code, start VS Code dan opnieuw.
Controleer of Pixi beschikbaar is:

```powershell
pixi --version
```

Er verschijnt een versienummer. Hebt u Pixi al, dan kunt u deze installatiestap
overslaan.

## 2. Open de Waterlagen-projectmap

Gebruik uw lokale Git-checkout van Waterlagen: de projectmap met `pixi.toml`,
`pixi.lock`, `pyproject.toml` en de map `src`. Bewaar de volledige checkout,
inclusief de verborgen map `.git`; de installatie bepaalt hiermee de pakketversie.

!!! note "Beschikbaarheid van de commandline-interface"
    De nieuwe `waterlagen`-opdrachten staan voorlopig alleen op de lokale
    werkbranch `feat/conda-forge-2026.2.2`. Gebruik de checkout van die branch.
    Een nieuwe download van `main` of versie `2026.2.1` bevat deze opdrachten
    nog niet. Hebt u deze checkout niet, vraag de projectbeheerder dan om toegang
    tot deze versie.

Ga in PowerShell naar de projectmap. Vervang het voorbeeldpad door uw eigen pad:

```powershell
cd D:/Repositories/waterlagen
```

Voer alle volgende opdrachten vanuit deze map uit. In VS Code kunt u deze map
openen en via **Terminal → New Terminal** een terminal starten.

## 3. Installeer de omgeving

```powershell
pixi install --environment afwateringseenheden --locked
```

De eerste installatie downloadt de benodigde software en kan enkele minuten
duren. Pixi bewaart deze in `.pixi` onder de projectmap. De omgeving
`afwateringseenheden` bevat ook PCRaster voor de afstroomrichtingberekening.
`--locked` gebruikt de pakketversies die in `pixi.lock` zijn vastgelegd.

## 4. Controleer de installatie

Kies een schrijfbare map voor uw gegevens. In de voorbeelden is dat
`D:/Waterlagen/data`; vervang die locatie zo nodig. Zet paden met spaties tussen
dubbele aanhalingstekens.

```powershell
pixi run --environment afwateringseenheden waterlagen --version
pixi run --environment afwateringseenheden waterlagen controleer --data-dir D:/Waterlagen/data
```

De controle voert een kleine rasterberekening uit en test het schrijven en lezen
van een bestand. Er worden geen brongegevens gedownload. Bij succes verschijnt
**Installatie OK**. Het getoonde versienummer volgt de Git-versie van uw checkout
en kan een ontwikkelversie zijn.

## 5. Waterlagen uitvoeren

Bekijk de beschikbare opdrachten:

```powershell
pixi run --environment afwateringseenheden waterlagen --help
```

Ga verder met [Afwateringseenheden produceren](afwateringseenheden.md).
Voor eigen Python-workflows kunt u het voorbeeld bij
[Eerste dataset produceren](eerste-dataset.md) volgen.

Bij een volgende sessie opent u opnieuw een terminal in dezelfde projectmap en
gebruikt u weer `pixi run --environment afwateringseenheden ...`. Pixi kiest
automatisch de juiste omgeving; apart activeren is niet nodig.

## Als een opdracht niet werkt

| Melding | Wat u kunt doen |
|---|---|
| `pixi` wordt niet herkend | Open een nieuwe terminal na installatie; herstart ook VS Code als u daarin werkt. |
| Pixi kan geen projectbestand vinden | Ga met `cd` naar de map waarin `pixi.toml` staat. |
| `waterlagen` wordt niet herkend | Gebruik de volledige `pixi run`-opdracht en controleer of uw checkout de commandline-interface bevat. |
| Geen toegang tot de datamap | Kies bij `--data-dir` een locatie waar u bestanden mag opslaan. |

Voor tests en wijzigingen aan de software, zie
[Ontwikkelomgeving](../bijdragen/ontwikkelomgeving.md).
