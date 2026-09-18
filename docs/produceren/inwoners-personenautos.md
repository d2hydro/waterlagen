# Inwoners en personenauto's voorbereiden

!!! warning "Vereist nieuwere broncode"
    Deze workflows en Pixi-taken zijn niet beschikbaar in release 2026.2.1 of
    de bijbehorende productie-TOML. Gebruik de broncoderepository `waterlagen`
    met de [ontwikkelomgeving](../bijdragen/ontwikkelomgeving.md) en voer de
    opdrachten hieronder vanuit die broncodemap uit.

De workflows voor inwoners en personenauto's starten met dezelfde bron- en
tussenproductstappen. Beide downloaden de CBS-bronnen alleen wanneer die nog
niet in de DataStore staan en bouwen alleen nieuwe VBO-buurtbestanden wanneer
die nog niet bestaan.

Voer een van de afzonderlijke workflows uit met Pixi:

```console
pixi run inwoners
pixi run auto
```

Vergelijk de CBS-totalen met de sommen van de verdeelde waarden met:

```console
pixi run statistiek_inwoners_autos
```

Daarvoor moet de landelijke BAG-light GeoPackage al beschikbaar zijn. Deze kan
worden opgehaald met:

```console
pixi run python scripts/bag.py
```

De scripts delen `processed_data/vbo_buurt/bag_vbo.gpkg` met geselecteerde
woon-VBO's en hun CBS-buurtcode, en
`processed_data/vbo_buurt/cbs_buurt.gpkg` met CBS-buurtpolygonen,
`aantal_woonvbo`, `aantal_inwoners`, `aantal_huishoudens` en
`personenautos_totaal`.

`pixi run inwoners` schrijft daarnaast
`processed_data/inwoners/inwoners.gpkg`. Dit
bestand bevat per woon-VBO de twee inwonersverdelingen
`inwoners_obv_huishoudens` en `inwoners_obv_woonvbo`. Zie
[Inwoners per woon-VBO](../bewerkingen/inwoners-per-vbo.md) voor de betekenis
en beperkingen van deze waarden.

Voor een aanvullend cloudgericht GeoParquet-bestand zet je bovenin
`scripts/inwoners.py` de optie `WRITE_GEOPARQUET = True`. De workflow schrijft
dan ook `processed_data/inwoners/inwoners.parquet`.

`pixi run auto` schrijft daarnaast `processed_data/autos/autos.gpkg`. Dit bestand
bevat per woon-VBO de gelijkmatig verdeelde waarde `personenautos`. Zie
[Personenauto's per woon-VBO](../bewerkingen/personenautos-per-vbo.md) voor de
betekenis en beperkingen van deze waarde. `pixi run autos` is een gelijkwaardige
alias voor dit script.

Voor de auto-uitvoer zet je op dezelfde manier `WRITE_GEOPARQUET = True` in
`scripts/auto.py`. Dan wordt ook `processed_data/autos/autos.parquet`
geschreven.
