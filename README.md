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
Gebruik **Pixi** om Waterlagen vanuit de projectmap te installeren en uit te
voeren. Pixi installeert ook Python, GDAL en PCRaster. Volg de
[installatiehandleiding](docs/produceren/installatie.md) voor het openen van de
juiste projectversie en het controleren van de installatie.

```console
pixi install --environment afwateringseenheden --locked
pixi run --environment afwateringseenheden waterlagen --help
```

## Aan de slag
Wanneer de gebruiker eenmalig een `data_dir` opgeeft voor de `DataStore`, worden hier alle downloads, bewerkingen en logs opgeslagen. Lees meer over de DataStore in de [documentatie](https://d2hydro.github.io/waterlagen/produceren/configuratie/)

### Downloaden
Het ondersteunen van de volgende lagen vanaf [PDOK](https://www.pdok.nl/) en [AHN.nl](https://www.ahn.nl/) wordt ondersteund:

* AHN 4 t/m 6
* BAG
* BGT

Lees verder in de [documentatie](https://d2hydro.github.io/waterlagen/produceren/eerste-dataset/)

### Bewerken
De volgende bewerkingen zijn beschikbaar:

* Dichtinterpoleren van AHN DTM
* Branden van BAG-panden op basis van AHN-hoogte

Lees verder in de [documentatie](https://d2hydro.github.io/waterlagen/bewerkingen/) 

## Ontwikkelaars
Waterlagen wordt ontwikkeld door [D2Hydro](https://d2hydro.nl/) en het [Hoogheemraadschap Hollands Noorderkwartier](https://www.hhnk.nl/) met als doel het gestandaardiseerd downloaden en bewerkingen van features en rasters via Python voor toepassingen in het waterbeheer.
