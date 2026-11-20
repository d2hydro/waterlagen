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

??? info "Eenmalig overstappen vanaf 2026.11.0"

    Oudere pakketten hebben nog `bijwerken.cmd` of `bijwerken.sh`. Die updater kan
    het uitgebreide productiepakket niet installeren. Zodra een nieuwe release
    met `waterlagen-updater.py` is gepubliceerd, kunt u onderstaande opdracht
    eenmalig uitvoeren vanuit uw **bestaande projectmap**.

    De opdracht haalt de nieuwe updater op naar een tijdelijke locatie. Bevestig
    daarna de update van uw bestaande installatie. Instellingen, eigen bestanden
    en gegevens blijven behouden. Bij een mislukte installatie wordt de vorige
    versie hersteld. Gebruik na een geslaagde overstap de gewone
    `code_bijwerken.bat` of `code_bijwerken.sh`.

    === "Windows (PowerShell)"

        Open PowerShell in de bestaande projectmap en voer dit blok uit:

        ```powershell
        & {
            $updaterRelease = Invoke-RestMethod -Uri 'https://api.github.com/repos/d2hydro/waterlagen/releases/latest' -ErrorAction Stop
            $updaterPath = Join-Path ([IO.Path]::GetTempPath()) ('waterlagen-updater-' + [guid]::NewGuid().ToString('N') + '.py')
            try {
                Invoke-WebRequest -Uri "https://github.com/d2hydro/waterlagen/releases/download/$($updaterRelease.tag_name)/waterlagen-updater.py" -OutFile $updaterPath -ErrorAction Stop
                pixi exec --spec "python=3.13" -- python $updaterPath --project-dir (Get-Location).Path --versie $updaterRelease.tag_name
            } finally {
                Remove-Item -LiteralPath $updaterPath -ErrorAction SilentlyContinue
            }
        }
        ```

    === "Linux"

        Open een terminal in de bestaande projectmap en voer dit blok uit:

        ```bash
        pixi exec --spec "python=3.13" -- python -c '
        import json
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        from urllib.request import urlopen

        with urlopen("https://api.github.com/repos/d2hydro/waterlagen/releases/latest", timeout=60) as response:
            tag = json.load(response)["tag_name"]
        with tempfile.TemporaryDirectory(prefix="waterlagen-updater-") as directory:
            updater = Path(directory) / "waterlagen-updater.py"
            url = f"https://github.com/d2hydro/waterlagen/releases/download/{tag}/waterlagen-updater.py"
            with urlopen(url, timeout=60) as response:
                updater.write_bytes(response.read())
            raise SystemExit(subprocess.call([sys.executable, str(updater), "--project-dir", str(Path.cwd()), "--versie", tag]))
        '
        ```

??? info "Als een opdracht niet werkt"

    <span id="als-een-opdracht-niet-werkt"></span>

    - **Pixi niet gevonden?** Open een nieuw terminalvenster na installatie.
    - **Projectbestand ontbreekt?** Open de map waarin `pixi.toml` en `pixi.lock` samen staan.
    - **Gegevensmap niet schrijfbaar?** Kies een [andere opslaglocatie](configuratie.md).
    - **Download geblokkeerd door een certificaatfout?** Zie [HTTPS-certificaatproblemen](https-certificaatproblemen.md).
