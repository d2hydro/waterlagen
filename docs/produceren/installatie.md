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
2. Klik in Verkenner met de rechtermuisknop op het ZIP-bestand en kies **Alles uitpakken**.
3. Open daarin de map **`waterlagen-productie-<tag>`** met **`pixi.toml`, `pixi.lock` en `scripts`**.
   Het versienummer blijft in deze mapnaam en in de pakketinhoud staan.
   Dit is uw **projectfolder**. U mag die map bijvoorbeeld `mijn-waterlagen` noemen.

!!! note "Beschikbaarheid"
    De downloadlink volgt de nieuwste stabiele release; prereleases vallen daar
    buiten. Voor een oudere versie of prerelease opent u de
    [Waterlagen-releases](https://github.com/d2hydro/waterlagen/releases) en kiest u
    het productiepakket onder **Assets**, niet **Source code (zip)**.
    Oudere productiepakketten kunnen nog een versienummer in de ZIP-naam hebben.
    De ZIP komt beschikbaar nadat de releasecontroles zijn geslaagd. Werkt de
    downloadlink niet, controleer dan bij de releases of het productiepakket al
    beschikbaar is.

De projectfolder bevat de installatiebestanden en scripts al op de juiste plaats.
U hoeft geen bestanden uit `envs` te kopiëren of scripts apart te downloaden:

```text
mijn-waterlagen/
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

### PowerShell openen in uw projectfolder

1. Open **Verkenner**.
2. Ga naar uw projectfolder, bijvoorbeeld `mijn-waterlagen`. In deze map ziet u
   `pixi.toml` en `pixi.lock`.
3. Klik bovenaan in de **adresbalk**, waar het pad naar de map staat.
4. Typ **`powershell`** en druk op **Enter**.

Er opent een PowerShell-venster dat opdrachten vanuit deze projectfolder uitvoert.
**Voer alle onderstaande opdrachten die met `pixi` beginnen uit in dit
PowerShell-venster.** Typ of plak één opdracht en druk op **Enter**. Wacht totdat
de opdracht klaar is voordat u de volgende uitvoert. U herkent dit doordat
PowerShell weer een regel toont die begint met `PS` en waarop u kunt typen.

Laat PowerShell tijdens de installatie en berekeningen open. Hebt u het venster
gesloten? Open het dan opnieuw vanuit dezelfde projectfolder met de stappen hierboven.

Python-code uit de voorbeelden slaat u op in een `.py`-bestand onder `scripts`.
Die code plakt u niet rechtstreeks in PowerShell. Het bijbehorende
`pixi run ...`-commando voert u wel in PowerShell uit.

## 3. Installeer de vastgelegde omgeving

```powershell
pixi install --locked
```

De eerste installatie download de software en kan enkele minuten duren.
Pixi bewaart deze in `.pixi` onder de projectfolder. `--locked` gebruikt de
pakketversies uit `pixi.lock`. Bewaar dit bestand samen met `pixi.toml`.
Internet is nodig voor installatie en voor het ophalen van brongegevens.

## 4. Controleer de installatie

```powershell
pixi run --locked controleer
```

De controle toont de geïnstalleerde releaseversie en de gegevensmap, importeert
de scripts en test een klein raster met GDAL, Rasterio en PCRaster.
Bij succes verschijnt **Imports en rastercontrole OK**.
Er worden geen brongegevens gedownload en geen productieworkflows gestart.

Gegevens komen standaard in `./data`, onder uw projectfolder. U hoeft niets in
te stellen. Zie [Opslag van gegevens](configuratie.md) voor een andere locatie.

## 5. Start een productie

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

Bij een volgende sessie opent u weer [PowerShell in uw projectfolder](#powershell-openen-in-uw-projectfolder).
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
