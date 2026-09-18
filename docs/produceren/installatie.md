# Installatie

Deze handleiding gebruikt de installatiebestanden in **`envs`** met
**Waterlagen 2026.2.1** uit PyPI. Pixi installeert Python en de benodigde GIS-bibliotheken, waaronder
GDAL. U hoeft Git of Python niet apart te installeren.
De configuratie ondersteunt Windows en Linux; de voorbeelden hieronder gebruiken
Windows PowerShell. De installatie is op Windows gecontroleerd.

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

## 2. Download en pak het productieproject uit

U krijgt de installatiebestanden samen in een ZIP-bestand. Clonen is niet nodig.

1. Open [de productie- en documentatiebranch op GitHub](https://github.com/d2hydro/waterlagen/tree/issue57_productie_waterlagen_ducumentatie).
   Kies voorlopig deze branch: de installatiebestanden in `envs` staan nog niet
   op de standaardbranch `main`.
2. Klik op de groene knop **Code** en daarna op **Download ZIP**.
3. Klik in Windows Verkenner met de rechtermuisknop op het gedownloade ZIP-bestand
   en kies **Alles uitpakken**. Kies een map waarin u het project wilt bewaren.
4. Open de uitgepakte map waarvan de naam begint met `waterlagen-`, en open daarin
   de submap **`envs`**. Hier staan **`pixi.toml` en `pixi.lock`** voor productie.

Bewaar beide bestanden in dezelfde map. `pixi.toml` beschrijft welke software
nodig is, waaronder Waterlagen 2026.2.1. `pixi.lock` legt de bijbehorende
pakketversies vast. U hoeft deze bestanden niet zelf te maken of aan te passen.
Gebruik de bestanden uit **`envs`**. De gelijknamige bestanden in de hoofdmap
zijn bedoeld voor ontwikkeling. In deze handleiding is `envs` uw
productieprojectmap. U kunt deze map ook los kopiëren naar een eigen werkmap;
de overige bestanden uit de ZIP zijn niet nodig om de release te gebruiken.

Hebt u de repository al lokaal? Open dan direct de submap `envs`; opnieuw
downloaden is niet nodig.

Klik in de adresbalk van Verkenner, typ `powershell` en druk op Enter. PowerShell
opent nu in deze map. Voer alle volgende opdrachten vanuit deze map uit.
In VS Code kunt u de uitgepakte map openen en via **Terminal → New Terminal**
een terminal starten.

## 3. Installeer de omgeving

```powershell
pixi install --locked
```

De eerste installatie download de benodigde software en kan enkele minuten
duren. Pixi bewaart deze in `.pixi` onder de productieprojectmap.
`--locked` gebruikt de pakketversies die in `pixi.lock` zijn vastgelegd.
Deze TOML gebruikt de standaardomgeving; u hoeft geen omgeving te kiezen.

## 4. Controleer de installatie

De voorbeelden gebruiken `./data`: de submap `data` in de productieprojectmap.
Voer de opdrachten daarom steeds vanuit die projectmap uit. De datamap wordt
automatisch aangemaakt. Zie [Configuratie en DataStore](configuratie.md) als u
de gegevens op een andere locatie wilt opslaan.

```powershell
pixi run controleer
```

De controle test of Waterlagen en de GIS-bibliotheken kunnen worden geladen.
Er worden geen brongegevens gedownload en geen rasterberekeningen uitgevoerd.
Bij succes verschijnen **Waterlagen 2026.2.1** en **Imports OK**. De opdracht
`controleer` is een taak in de productie-TOML.

## 5. Waterlagen uitvoeren

Ga verder met [Eerste dataset produceren](eerste-dataset.md): u slaat een kort
AHN-voorbeeld op als `eerste_dataset.py` in de productieprojectmap en voert het uit:

```powershell
pixi run python eerste_dataset.py
```

Bij een volgende sessie opent u opnieuw een terminal in dezelfde projectmap en
gebruikt u weer `pixi run ...`. Pixi kiest
automatisch de juiste omgeving; apart activeren is niet nodig.

## Beschikbaar in deze release

De AHN-, BAG- en BGT-functies zijn beschikbaar in versie 2026.2.1. De instructies
voor DGM1, afwateringseenheden en inwoners/personenauto's gebruiken nieuwere
broncode en werken niet met deze productie-TOML. Die pagina's vermelden dit
bovenaan. Ook de API-referentie beschrijft de broncodeversie van deze documentatie;
daarin kunnen functies staan die nog niet in 2026.2.1 zitten.

## Als een opdracht niet werkt

| Melding | Wat u kunt doen |
|---|---|
| `pixi` wordt niet herkend | Open een nieuwe terminal na installatie; herstart ook VS Code als u daarin werkt. |
| Pixi kan geen projectbestand vinden | Ga met `cd` naar de map waarin `pixi.toml` staat. |
| `pixi.lock` ontbreekt | Pak de ZIP volledig uit en controleer of `pixi.toml` en `pixi.lock` in dezelfde map staan. Ontbreekt een bestand ook in de ZIP, vraag dan de beheerder om de complete ZIP. |
| De taak `controleer` ontbreekt | Open de submap `envs` met de productieconfiguratie; de hoofdmap gebruikt de ontwikkelconfiguratie. |
| Python kan een script niet vinden | Sla het voorbeeld op in de productieprojectmap en voer de opdracht vanuit die map uit. |
| Geen toegang tot de datamap | Stel in `.datastore` een locatie in waar u bestanden mag opslaan; zie [Configuratie](configuratie.md). |

Voor tests en wijzigingen aan de software, zie
[Ontwikkelomgeving](../bijdragen/ontwikkelomgeving.md).
