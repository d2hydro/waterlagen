# Installatie

Met het **productiepakket** van een Waterlagen-release kunt u zelfstandig
afwateringseenheden, functioneel landgebruik, inwoners en personenauto's produceren.
Het pakket bevat Pixi-installatiebestanden en de bijbehorende Python-scripts.
Toegang tot een private repository is niet nodig.

Pixi installeert de Waterlagen-versie die bij het pakket hoort, Python en de
GIS-bibliotheken, inclusief GDAL en PCRaster. U hoeft Git of Python niet apart
te installeren. Het pakket ondersteunt Windows en Linux; hieronder gebruiken
we Windows PowerShell.

## 1. Installeer Pixi

Open de [installatiepagina van Pixi](https://pixi.prefix.dev/latest/installation/)
en kies op Windows de **Windows Installer**. Voer de installer uit.
Open daarna het Windows-startmenu, typ **PowerShell** en open **Windows PowerShell**.
Dit is een venster waarin u opdrachten kunt typen of plakken.
Werkt u in VS Code, start VS Code dan opnieuw na de installatie.

Typ of plak onderstaande opdracht in PowerShell en druk op **Enter**:

```powershell
pixi --version
```

Er verschijnt een versienummer. Hebt u Pixi al, dan kunt u deze installatiestap overslaan.

## 2. Download het productiepakket

1. Download [**waterlagen-productie.zip**](https://github.com/d2hydro/waterlagen/releases/latest/download/waterlagen-productie.zip)
   van de nieuwste stabiele release.
2. Pak de inhoud van de zip-file uit in een projectfolder naar keuze, bijvoorbeeld
   `waterlagen-productie`. De bestanden en de map `scripts` staan direct in de zip,
   zonder extra bovenliggende map. Kies een locatie met voldoende schijfruimte
   voor de lagen die u wilt produceren.

!!! note "Versies en beschikbaarheid"
    De downloadlink volgt de nieuwste stabiele release. Wilt u een andere versie, ga dan naar
    [waterlagen releases](https://github.com/d2hydro/waterlagen/releases) en download`waterlagen-productie.zip` onder de `assets` van de juiste release. De productie is beschikbaar vanaf release 2026.9.0

De projectfolder bevat de installatiebestanden en scripts al op de juiste plaats.
U hoeft geen bestanden uit `envs` te kopiëren of scripts apart te downloaden:

```text
waterlagen-productie/
├── README.md
├── LICENSE
├── pixi.toml
├── pixi.lock
├── .datastore
└── scripts/
    ├── controleer_productie.py
    ├── afwateringseenheden.py
    ├── functioneel_landgebruik.py
    ├── bag.py
    ├── inwoners.py
    ├── auto.py
    └── statistiek_inwoners_autos.py
```

De meegeleverde `.datastore` bevat `DATA_DIR=./data`. Laat dit bestand staan.
Pixi maakt later de map `.pixi` aan; Waterlagen maakt `data` voor uw gegevens.
De locatie van uw projectfolder kiest u zelf.

## 3. Installeer en controleer de omgeving

Voer vanuit uw projectfolder de volgende opdracht uit. Pixi installeert bij de
eerste uitvoering automatisch de omgeving in `.pixi`. Dit vereist internet en
kan enkele minuten duren.

```powershell
pixi run --locked controleer
```

!!! note "Waarom `--locked`?"
    `--locked` voorkomt dat Pixi het meegeleverde `pixi.lock` wijzigt en stopt
    als het ontbreekt of niet bij `pixi.toml` past. Zo blijven de pakketversies
    behouden die bij de release zijn getest.

De controle toont de geïnstalleerde releaseversie en de gegevensmap, importeert
de scripts en test een klein raster met GDAL, Rasterio en PCRaster.
Bij succes verschijnt **Imports en rastercontrole OK**.
Er worden geen brongegevens gedownload en geen productieworkflows gestart.

Gegevens komen standaard in `./data`, onder uw projectfolder. U hoeft niets in
te stellen. Zie [Opslag van gegevens](configuratie.md) voor een andere locatie.

## 4. Start een productie

Kies één productie. Lees eerst de bijbehorende uitleg en controleer de
instellingen in het script voor uw toepassing:

| Productie | Opdracht | Uitleg |
|---|---|---|
| Afwateringseenheden (standaard Aa en Maas) | `pixi run --locked afwateringseenheden` | [Afwateringseenheden](afwateringseenheden.md) |
| Functioneel landgebruik (landelijk) | `pixi run --locked landgebruik` | [Landgebruik](landgebruik.md) |
| Inwoners per woon-VBO (landelijk) | `pixi run --locked inwoners` | [Inwoners en auto's](inwoners-personenautos.md) |
| Personenauto's per woon-VBO (landelijk) | `pixi run --locked auto` | [Inwoners en auto's](inwoners-personenautos.md) |

Dit zijn volledige producties die veel gegevens kunnen downloaden en veel
rekentijd en schijfruimte kunnen vragen. De scripts zijn voorbeelden die u kunt
aanpassen. Beoordeel de resultaten voordat u ze gebruikt.

Voer ook bij een volgende sessie de opdrachten vanuit uw projectfolder uit.
U hoeft de omgeving niet apart te activeren.

## Als een opdracht niet werkt

| Melding | Wat u kunt doen |
|---|---|
| `pixi` wordt niet herkend | Open PowerShell opnieuw na installatie; herstart ook VS Code als u daarin werkt. |
| Pixi kan geen projectbestand vinden | Open PowerShell in de uitgepakte map met `pixi.toml`. |
| `pixi.lock` ontbreekt of past niet bij `pixi.toml` | Pak het productiepakket opnieuw uit in een nieuwe map; gebruik de bestanden van dezelfde release. |
| Een productietaak ontbreekt | Controleer of u het productiepakket hebt gedownload en PowerShell in de juiste map hebt geopend. |
| Geen toegang tot de datamap | Kies een schrijfbare [opslaglocatie](configuratie.md). |

Voor tests en wijzigingen aan Waterlagen zelf, zie
[Ontwikkelomgeving](../bijdragen/ontwikkelomgeving.md).
