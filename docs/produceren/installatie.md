---
editorial_status: ai
---

# Installatie

## 1. Installeer Pixi

Kies op Windows de **Windows Installer**.

[Pixi installeren](https://pixi.prefix.dev/latest/installation/){ .md-button }

## 2. Download het productiepakket

[Download het productiepakket](https://github.com/d2hydro/waterlagen/releases/latest/download/waterlagen-productie.zip){ .md-button .md-button--primary }

Pak `waterlagen-productie.zip` uit in een map met voldoende ruimte voor de brongegevens en kaarten.

## 3. Installeer en controleer de omgeving

Open de uitgepakte map in Windows Verkenner. Typ `cmd` in de adresbalk en druk op Enter. U kunt ook PowerShell of op Linux een terminal in die map openen. Voer één keer uit:

```console
pixi run --locked controleer
```

Wacht op **Imports en rastercontrole OK**. De eerste installatie vereist internet.

## 4. Start een productie

[Kaart maken met de Run Maker](index.md){ .md-button .md-button--primary }

## Bijwerken bestaande installatie

Gebruik vóór een nieuwe productie `code_bijwerken.bat` (Windows) of `sh ./code_bijwerken.sh` (Linux) om een nieuwe release te installeren. Bevestig de update. Uw instellingen en gegevens blijven behouden. Rond lopende producties eerst af en hervat onderbroken runs met de oorspronkelijke versie.

??? info "Als een opdracht niet werkt"

    <span id="als-een-opdracht-niet-werkt"></span>

    - **Pixi niet gevonden?** Open een nieuw terminalvenster na installatie.
    - **Projectbestand ontbreekt?** Open de map waarin `pixi.toml` en `pixi.lock` samen staan.
    - **Gegevensmap niet schrijfbaar?** Kies een [andere opslaglocatie](configuratie.md).
    - **Download geblokkeerd door een certificaatfout?** Zie [HTTPS-certificaatproblemen](https-certificaatproblemen.md).
