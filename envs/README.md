# Waterlagen produceren

Pakketversie: @VERSION@

## Eenmalig installeren

1. Installeer [Pixi](https://pixi.prefix.dev/latest/installation/) en pak de ZIP uit.
2. Open een terminal in de uitgepakte map met `pixi.toml` en voer uit:

```console
pixi run --locked controleer
```

De installatie is klaar bij **Imports en rastercontrole OK**.

## Een kaart maken

1. Dubbelklik op **run-maken.bat**. Bij de eerste start zet Pixi zo nodig de omgeving klaar. Kies daarna je datastore. Klik op het mapicoon naast een pad om de locatie te wijzigen.
2. Klik op **Runmaker openen**. De kaart opent op Windows in een eigen venster met het Waterlagen-logo. Kies het gebied en de kaartlagen.
3. Vul de **Runnaam** in. Kies zo nodig een andere uitvoermap met **Resultatenmap kiezen…**.
4. Klik op **Opslaan en starten**. Met **Alleen opslaan** bewaar je het runscript voor later.

## Resultaten vinden

| Waar | Wat staat er? |
| --- | --- |
| `source_data/` | Gedownloade bronbestanden voor hergebruik. |
| `processed_data/<laag>/<gebied>/<runnaam>/` | De kaart, `run.json` met de runstatus en `productie.log` met het rekenverloop. |

Bij een eigen resultatenmap staat de run onder `<resultatenmap>/<laag>/<gebied>/<runnaam>/`.

[Werken via de terminal of op Linux](https://d2hydro.github.io/waterlagen/produceren/cli/) · [Waterlagen bijwerken](https://d2hydro.github.io/waterlagen/produceren/installatie/#bijwerken-bestaande-installatie)
