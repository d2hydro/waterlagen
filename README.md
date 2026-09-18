# Waterlagen
Deze module is bedoeld om alle GIS basislagen (rasters en features) te `downloaden` en te `bewerken` voor typische water-toepassingen.

[![Tests](https://github.com/d2hydro/waterlagen/actions/workflows/test-cov.yml/badge.svg)](https://github.com/d2hydro/waterlagen/actions/workflows/test-cov.yml)
[![Coverage](https://img.shields.io/codecov/c/github/d2hydro/waterlagen)](https://app.codecov.io/github/d2hydro/waterlagen)
[![Ruff Styling/Linting](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Release: latest](https://img.shields.io/github/v/release/d2hydro/waterlagen?include_prereleases)](https://pypi.org/project/waterlagen)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

**Documentatie**: [https://d2hydro.github.io/waterlagen](https://d2hydro.github.io/waterlagen)

**Broncode**: [https://github.com/d2hydro/waterlagen](https://github.com/d2hydro/waterlagen)

## Installeren
Download het **productiepakket** (`waterlagen-productie-<tag>.zip`) uit de
Assets van een [Waterlagen-release](https://github.com/d2hydro/waterlagen/releases).
Het pakket bevat scripts voor afwateringseenheden, landgebruik, inwoners en auto's,
plus een Pixi-omgeving die de bijbehorende release uit PyPI installeert.
Volg de [installatiehandleiding](docs/produceren/installatie.md), pak de ZIP uit
en open PowerShell in de map met `pixi.toml`:

```console
pixi install --locked
pixi run --locked controleer
```

Git of toegang tot een private repository is niet nodig. De release-workflow
voegt de ZIP toe na controles op Windows en Linux; oudere releases hebben dit
asset nog niet. Voor aanpassingen aan Waterlagen zelf gebruikt u de
[ontwikkelomgeving](docs/bijdragen/ontwikkelomgeving.md).

## Aan de slag
Waterlagen slaat downloads en resultaten automatisch op in de submap `data` van
uw projectfolder. U hoeft hiervoor niets in te stellen. Wilt u een andere locatie
gebruiken? Zie [Opslag van gegevens](docs/produceren/configuratie.md).

### Downloaden
Het ondersteunen van de volgende lagen vanaf [PDOK](https://www.pdok.nl/) en [AHN.nl](https://www.ahn.nl/) wordt ondersteund:

* AHN 4 t/m 6
* BAG
* BGT

Lees verder bij de [bronnen](docs/bronnen/index.md).

### Bewerken
De volgende bewerkingen zijn beschikbaar:

* Dichtinterpoleren van AHN DTM
* Branden van BAG-panden op basis van AHN-hoogte

Lees verder in de [documentatie](https://d2hydro.github.io/waterlagen/bewerkingen/) 

## Ontwikkelaars
Waterlagen wordt ontwikkeld door [D2Hydro](https://d2hydro.nl/) en het [Hoogheemraadschap Hollands Noorderkwartier](https://www.hhnk.nl/) met als doel het gestandaardiseerd downloaden en bewerkingen van features en rasters via Python voor toepassingen in het waterbeheer.
