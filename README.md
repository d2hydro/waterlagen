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


## Zelf produceren
Voor het zelf produceren van waterlagen zie de [documentatie](https://d2hydro.github.io/waterlagen/produceren). Hierin wordt deze module automatisch geinstalleerd.

## Zelf installeren
Zorg voor een conda (of pixi) met de juiste ondersteunende packages zie [dependencies] in de [pyproject.toml](https://github.com/d2hydro/waterlagen/blob/main/pyproject.toml). Voeg hier waterlagen toe met

```
pip install waterlagen
```

## Lagen
Lagen worden altijd geconverteerd naar GeoTIFF (raster) en GeoPackage (features). Voor efficient gebruikt in de cloud wordt met Cloud-Optimized-GeoTiff (COG) en GeoParquet gewerkt.

### Bronnen
Bij het downloaden van  Vanaf [PDOK](https://www.pdok.nl/), [AHN.nl](https://www.ahn.nl/), [CBS](https://www.cbs.nl) en [NHI](https://nhi.nu/data/oppervlaktewater/hydamo-regionaal) kan worden gedownload:

* AHN 4 t/m 6
* BAG
* Beheerregisters van de waterschappen
* BGT
* BRP
* CBS buurten (inwoners, huishoudens en personenautos)
* Diverse administratieve grenzen (landsgrens, waterschapsgrenzen, etc)
* Dijkringen

Lees verder bij de [bronnen](docs/bronnen/index.md).

### Bewerken
De volgende bewerkingen zijn beschikbaar:

* Dichtinterpoleren van AHN DTM
* Branden van BAG-panden op basis van AHN-hoogte
* Productie van lagen voor de waterschadeschatter (functioneel_landgebruik, inwoners en autos)
* Afwateringseenheden

Lees verder in de [documentatie](https://d2hydro.github.io/waterlagen/bewerkingen/) 

## Ontwikkelaars
Waterlagen wordt ontwikkeld door [D2Hydro](https://d2hydro.nl/) en het [Hoogheemraadschap Hollands Noorderkwartier](https://www.hhnk.nl/) en [Waterschap Aa en Maas](https://www.aaenmaas.nl/) met als doel het gestandaardiseerd downloaden en bewerkingen van features en rasters via Python voor toepassingen in het waterbeheer.
