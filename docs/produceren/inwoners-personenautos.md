---
editorial_status: ai
---

# Inwoners en personenauto’s produceren

Kies **Inwoners** of **Auto's** in de [Run Maker](index.md). Ook voor een klein gebied worden landelijke BAG- en CBS-gegevens voorbereid. Beide kaarten gebruiken dezelfde voorbereiding.

Het gebied selecteert volledige CBS-buurten. Punten uit die buurten kunnen buiten de gekozen gebiedsgrens liggen.

## Uitvoer

De resultaten staan in `processed_data/<product>/<gebied>/<run-id>/`:

- `inwoners.gpkg` en `inwoners.parquet` bevatten `inwoners_obv_huishoudens` en
  `inwoners_obv_woonvbo`. Zie [Inwoners](../bewerkte-lagen/inwoners.md).
- `autos.gpkg` en `autos.parquet` bevatten `personenautos`.
  Zie [Auto's](../bewerkte-lagen/autos.md).

De productiemap bevat ook `productie.log` en `run.json`.
Voor regionale producties bevat `input/` de geselecteerde volledige buurtcontext.

[De uitkomsten vergelijken met CBS-totalen](../reference/vbo_buurt.md#verdelingen-controleren){ .md-button }
