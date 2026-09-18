# Configuratie en DataStore

`DataStore` bepaalt waar Waterlagen bronbestanden, verwerkte resultaten en logs
opslaat. Kies bij gebruik van de commandline een hoofdmap:

```console
waterlagen controleer --data-dir D:/Waterlagen/data
waterlagen afwateringseenheden --waterschap 38 --data-dir D:/Waterlagen/data --workers 2
```

De tweede opdracht start de productie voor het hele beheergebied van Aa en Maas.
Zie [Afwateringseenheden produceren](afwateringseenheden.md) voor de voorbereiding.

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

Zonder opslagconfiguratie gebruikt een geïnstalleerd pakket `data` onder de
huidige werkmap. Bij werken vanuit de broncode is dat `data` in de repository-root.
Een checkout leest ook `.datastore` uit de repository-root; het bestand in de
huidige werkmap heeft voorrang. Opslagmappen worden bij uitvoering aangemaakt;
`waterlagen --help` maakt geen datamappen aan.

## Parallel rekenen

Met `--workers 2` gebruikt de productie twee processen. Zonder die optie volgt
het aantal processen `AFWATERINGSEENHEDEN_WORKERS` uit uw omgeving of `.env` in de
huidige werkmap, standaard vier. Meer processen vragen meer werkgeheugen.

De technische eigenschappen staan in de [DataStore-API](../reference/datastore.md).
