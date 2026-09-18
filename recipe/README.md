# Conda-package en release

De eerste conda-forge-release is voorbereid als **2026.2.2**, met
**DanielTollenaar** als maintainer. Het recept in `recipe/recipe.yaml` bouwt
de huidige checkout. Het is nog niet ingediend bij conda-forge.
Deze publicatieroute is voorlopig uitgesteld. De gebruikersdocumentatie beschrijft
alleen [installatie met Pixi](../docs/produceren/installatie.md).

## Lokaal bouwen en testen

Voer vanuit de repository-root uit:

```console
pixi exec --spec rattler-build=0.76.1 rattler-build build --recipe recipe/recipe.yaml --output-dir .cache/conda-build
pixi exec --spec rattler-index=0.31.5 rattler-index fs .cache/conda-build --force
```

Rattler-build bouwt een `noarch: python`-pakket. De GIS-bibliotheken komen als
platformafhankelijke dependencies uit conda-forge. PCRaster blijft optioneel:
alleen de test van de afwateringseenheden-installatie voegt het toe.

De bouw controleert in aparte installatieomgevingen:

- imports van het geïnstalleerde pakket en de afhankelijkheden met `pip check`;
- de commandline-interface, inclusief versienummer en hulp;
- opslag buiten een broncode-checkout, zonder schrijven in de Python-installatie;
- een kleine PCRaster-berekening en het schrijven en lezen van een GeoTIFF.

Deze controles downloaden geen brondata en voeren geen volledige gebiedsproductie
uit. De workflow `.github/workflows/conda-package.yml` herhaalt de bouw op Windows
en Linux bij pull requests en kan ook handmatig worden gestart.

De tweede opdracht maakt de kanaalindex opnieuw aan. Dit is ook nodig na een
herbouw met dezelfde pakketnaam: anders kan de index nog de hash van een eerder
gebouwd pakket bevatten.

Het resultaat staat in `.cache/conda-build/noarch/`. Geef gebruikers het lokale
kanaal met `noarch/*.conda` en `noarch/repodata.json`, met behoud van de
mapstructuur. De tijdelijke bouwmappen hoeven niet mee. Bouwuitvoer blijft
buiten Git. Voor een latere handmatige pakkettest kan dit kanaal aan Conda worden
meegegeven met `--channel <pad-naar-kanaal>` naast `--channel conda-forge`.

## Publiceren

1. Laat de code en documentatie beoordelen en controleer de tests. Publiceer
   vervolgens release `2026.2.2` vanaf de beoordeelde commit. De bestaande
   releaseworkflow bouwt de Python-distributies en publiceert op PyPI.
   De release-tag bepaalt daarbij de pakketversie; het conda-recept gebruikt
   `context.version` en moet daarmee overeenkomen.
2. Download het **gepubliceerde bronarchief** van die versie van PyPI en noteer
   de SHA256. Op Windows kan dat met
   `Get-FileHash waterlagen-2026.2.2.tar.gz -Algorithm SHA256`.
3. Kopieer `recipe.yaml` en `run_test.py` naar
   `recipes/waterlagen/` in een eigen fork van
   [conda-forge/staged-recipes](https://github.com/conda-forge/staged-recipes).
   Vervang in het gekopieerde recept de volledige lokale `source`-sectie door:

   ```yaml
   source:
     url: https://pypi.org/packages/source/w/waterlagen/waterlagen-${{ version }}.tar.gz
     sha256: VERVANG_DOOR_SHA256_VAN_HET_GEPUBLICEERDE_BRONARCHIEF
   ```

4. Bouw ook dit recept met rattler-build. Hiermee wordt de gepubliceerde bron
   getest, inclusief de controle van de hash. Gebruik geen lokale `path`-bron
   voor de aanmelding.
5. Dien een pull request in bij staged-recipes met `DanielTollenaar` als
   `recipe-maintainers`. Volg de
   [conda-forge-bijdrageprocedure](https://conda-forge.org/docs/maintainer/adding_pkgs/).
   Na acceptatie wordt de feedstock ingericht en wordt het pakket gebouwd en
   gepubliceerd. Het GitHub-releaseproces alleen publiceert niet op conda-forge.
6. Controleer na publicatie de Conda-installatie op een schone machine. Voeg pas
   daarna deze installatieroute aan de gebruikershandleiding toe.

Volgende conda-releases worden via de feedstock onderhouden. Houd versie,
bronhash, dependencies en pakkettests bij elkaar. Een `noarch`-pakket bevat
platformonafhankelijke Waterlagen-code; beschikbaarheid van GIS-dependencies
bepaalt op welke platforms het daadwerkelijk geïnstalleerd kan worden.
