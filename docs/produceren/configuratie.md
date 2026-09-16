# Configuratie en DataStore

`DataStore` bepaalt waar Waterlagen bronbestanden, verwerkte resultaten en logs
opslaat. Zonder configuratie is de hoofdmap `data` in de repository-root. Daarin
staan `source_data` voor downloads en `processed_data` voor resultaten.

Stel een andere locatie in met een `.datastore`-bestand in de repository-root of
de huidige werkmap:

```text
DATA_DIR=pad/naar/mijn/data
SOURCE_DATA_DIR=pad/naar/mijn/brongegevens
PROCESSED_DATA_DIR=pad/naar/mijn/bewerkte-gegevens
```

Een `.datastore` in de huidige werkmap heeft voorrang. `SOURCE_DATA_DIR` en
`PROCESSED_DATA_DIR` zijn optioneel; zonder deze waarden gebruikt Waterlagen
submappen van `DATA_DIR`.

De technische eigenschappen staan in de [DataStore-API](../reference/datastore.md).
