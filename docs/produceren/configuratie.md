# Configuratie en DataStore

`DataStore` bepaalt waar Waterlagen bronbestanden, verwerkte resultaten en logs
opslaat. Kies bij gebruik van de commandline een hoofdmap. Voer deze opdrachten
uit vanuit de projectmap, na de [installatie met Pixi](installatie.md):

```console
pixi run --environment afwateringseenheden waterlagen controleer --data-dir D:/Waterlagen/data
```

Geef dezelfde `--data-dir` mee bij het
[produceren van afwateringseenheden](afwateringseenheden.md).

Met `--data-dir` komen downloads in `source_data` en resultaten in
`processed_data` onder deze map. Deze optie heeft voorrang op alle andere
opslaginstellingen, ook afzonderlijk ingestelde bron- en resultaatmappen.
Gebruik bij volgende opdrachten dezelfde locatie om downloads te hergebruiken.

## Vaste opslaglocatie

Om de locatie niet bij iedere opdracht te hoeven meegeven, maakt u een tekstbestand
met de naam `.datastore` in de map van waaruit u Waterlagen uitvoert. Let erop
dat de bestandsnaam niet eindigt op `.txt`.

```text
DATA_DIR=D:/Waterlagen/data
```

Optioneel kunt u daarin `SOURCE_DATA_DIR` en `PROCESSED_DATA_DIR` opgeven om
bronnen en resultaten op verschillende locaties te bewaren. Omgevingsvariabelen
met deze namen hebben voorrang op het bestand. Gebruik bij voorkeur absolute
paden; relatieve paden worden vanaf de huidige werkmap geïnterpreteerd.

Zonder opslagconfiguratie gebruikt deze Pixi-route `data` onder de projectmap.
Waterlagen leest `.datastore` uit de projectmap en de huidige werkmap; het
bestand in de huidige werkmap heeft voorrang. Opslagmappen worden bij uitvoering
aangemaakt. Het opvragen van hulp met `--help` maakt geen datamappen aan.

## Parallel rekenen

Met `--workers 2` gebruikt de productie twee processen. Zonder die optie volgt
het aantal processen `AFWATERINGSEENHEDEN_WORKERS` uit uw omgeving of `.env` in de
huidige werkmap, standaard vier. Meer processen vragen meer werkgeheugen.

De technische eigenschappen staan in de [DataStore-API](../reference/datastore.md).
