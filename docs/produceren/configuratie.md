# Configuratie en DataStore

Deze pagina hoort bij Waterlagen **2026.2.1** met de configuratie uit `envs`.
Die map (of uw losse kopie ervan) is de productieprojectmap.
`DataStore` bepaalt waar Waterlagen bronbestanden, verwerkte resultaten en logs
opslaat. Zonder aanpassingen gebruikt Waterlagen de submap `data` in de
projectmap. Downloads komen in `data/source_data` en resultaten in
`data/processed_data`. Voer de Pixi-opdrachten steeds vanuit de projectmap uit.
Gebruik bij volgende opdrachten dezelfde opslaglocatie om downloads te hergebruiken.

## Vaste opslaglocatie

Wilt u de locatie expliciet instellen, maak dan een tekstbestand met de naam
`.datastore` in de productieprojectmap. Sla het op als UTF-8 zonder BOM en
let erop dat de bestandsnaam niet eindigt op `.txt`.

```text
DATA_DIR=./data
```

`./data` verwijst naar de submap `data` in de huidige werkmap. Voor opslag op een
andere schijf kunt u bijvoorbeeld `DATA_DIR=D:/Waterlagen/data` invullen.

Optioneel kunt u daarin `SOURCE_DATA_DIR` en `PROCESSED_DATA_DIR` opgeven om
bronnen en resultaten op verschillende locaties te bewaren. Omgevingsvariabelen
met deze namen hebben voorrang op het bestand. Ook hier worden relatieve paden
vanaf de huidige werkmap geïnterpreteerd. Gebruik een absoluut pad als u de
gegevens buiten de projectmap wilt opslaan.

Versie 2026.2.1 leest `.datastore` uit de huidige werkmap. Zonder
opslagconfiguratie gebruikt deze versie `data` onder die map. Waterlagen maakt
opslagmappen automatisch aan.

Neem geen `.env` over uit een ontwikkelomgeving met nieuwere workflows.
Instellingen zoals `AFWATERINGSEENHEDEN_WORKERS` bestaan nog niet in 2026.2.1 en
kunnen bij het laden een configuratiefout veroorzaken. Voor het AHN-voorbeeld
hoeft u geen `.env` te maken.

De [DataStore-API](../reference/datastore.md) beschrijft de huidige broncode;
nieuwere eigenschappen zijn niet allemaal beschikbaar in release 2026.2.1.
