# Inwoners en personenauto's produceren

Installeer het [productiepakket](installatie.md) en voer vanuit de projectfolder uit:

```console
pixi run --locked inwoners --area alkmaar --run-id voorbeeld
pixi run --locked autos --area alkmaar --run-id voorbeeld
```

Beide workflows halen BAG-light, CBS Wijk- en Buurtkaart en CBS Kerncijfers op.
Zij delen de voorbereiding in `processed_data/vbo_buurt/`. Die wordt hergebruikt
zolang de bronidentiteit overeenkomt. Met `--refresh-sources` voor een nieuwe run
worden de bronnen vernieuwd en afhankelijke caches zo nodig opnieuw opgebouwd.
Ook een regionale productie gebruikt deze landelijke bronvoorbereiding.

Het gebied selecteert volledige CBS-buurten, inclusief alle woon-VBO's in die
buurten. De verdeling gebruikt daardoor dezelfde aantallen als een landelijke
productie. Resultaten worden niet op de gebiedsgrens geknipt.
Zie [gedeelde opties en gebieden](cli.md) voor Nederland, waterschapscodes,
offline gebruik en hervatten.

## Uitvoer

De resultaten staan in `processed_data/<product>/<gebied>/<run-id>/`:

- `inwoners.gpkg` en `inwoners.parquet` bevatten `inwoners_obv_huishoudens` en
  `inwoners_obv_woonvbo`. Zie [Inwoners per woon-VBO](../bewerkingen/inwoners-per-vbo.md).
- `autos.gpkg` en `autos.parquet` bevatten `personenautos`.
  Zie [Personenauto's per woon-VBO](../bewerkingen/personenautos-per-vbo.md).

GeoParquet wordt standaard geschreven; `--no-geoparquet` schrijft alleen
GeoPackage. De productiemap bevat ook `productie.log` en `run.json`.
Voor regionale producties bevat `input/` de geselecteerde volledige buurtcontext.

CBS-totalen en verdeelde waarden vergelijken kan via de
[Python-statistiekfunctie](../reference/gebruik.md#verdelingen-controleren).
Gebruik daarbij de buurten en resultaten van hetzelfde gebied.
