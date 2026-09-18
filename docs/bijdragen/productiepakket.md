# Productiepakket bij een release

De bestaande GitHub-workflow `release.yml` start wanneer een GitHub Release wordt
gepubliceerd. De tag bepaalt de pakketversie via `hatch-vcs`; we behouden het
bestaande CalVer-patroon uit `pyproject.toml`, inclusief optionele `v` en prereleases.
De workflow maakt zelf geen tag of release.

Na tests, de wheel/sdist-build en publicatie op PyPI bouwt
`tools/build_production_bundle.py` het productiepakket. De versie komt uit dezelfde
releasetag. De generator leest de runtime-dependencies en de PCRaster-feature uit
de hoofd-`pixi.toml`, vult `envs/pixi.toml.in` in en kopieert alleen de expliciet
geselecteerde scripts uit `scripts/`, de README-template uit `envs` en de licentie.
De scripts worden dus op één plek onderhouden. Een publieke `.datastore` met
`DATA_DIR=./data` wordt gegenereerd; lokale instellingen worden nooit gekopieerd.

`pixi lock` legt alle dependencies voor Windows en Linux vast, met de exacte
Waterlagen-release uit PyPI. Het lockbestand van de ontwikkelomgeving wordt niet
gebruikt: daarin staat een lokale editable dependency. De productie-lock wordt bij
de release gegenereerd en samen met de scripts in de ZIP bewaard. Gebruikers
installeren vervolgens met `pixi install --locked`.

De workflow pakt de ZIP uit op Windows en Linux, zonder checkout van de repository,
en test installatie, scriptimports en een kleine rasterberekening. Pas als beide
controles slagen wordt `waterlagen-productie-<tag>.zip` aan de GitHub Release
toegevoegd. De uploadjob heeft als enige nieuwe job `contents: write` nodig.
Een mislukte bundeltest draait een al gepubliceerde PyPI-release niet terug.

## Lokaal controleren

Gebruik een versie die al op PyPI staat en scripts die bij die versie passen.
Voer vanuit de repository uit, bijvoorbeeld voor de bestaande testrelease:

```powershell
pixi run python ./tools/build_production_bundle.py --tag 2026.9.0rc1 --output-dir ./dist
```

Pak de ZIP uit in een aparte folder en volg de meegeleverde README.
De generator vereist alleen Python 3.11 of hoger en Pixi; hij installeert de
productieomgeving niet zelf. Voor testen gebruiken we dezelfde Pixi-versie als
de release-workflow (0.70.1).

De builder weigert ongeldige tags en lokale of private packageverwijzingen in
het lockbestand. Alleen de allowlist wordt ingepakt; caches, data, `.env`,
repositorycode en machineconfiguratie worden niet meegenomen.

Bij vertraging van de PyPI-index probeert de release-workflow de build opnieuw.
Een reeds geüploade release-ZIP wordt niet stilzwijgend vervangen. Een opnieuw
gegenereerd lockbestand kan later andere dependencyversies kiezen; behoud daarom
het geteste asset voor die release.

De controle voert geen volledige landelijke productie uit. De inhoudelijke
validatie van geproduceerde datasets blijft nodig.
