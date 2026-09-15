# Inwoners en personenauto's voorbereiden

De workflows voor inwoners en personenauto's starten met dezelfde bron- en
tussenproductstappen. Beide downloaden de CBS-bronnen alleen wanneer die nog
niet in de DataStore staan en bouwen alleen nieuwe VBO-buurtbestanden wanneer
die nog niet bestaan.

Voer een van de afzonderlijke workflows uit met Pixi:

```console
pixi run inwoners
pixi run auto
```

Daarvoor moet de landelijke BAG-light GeoPackage al beschikbaar zijn. Deze kan
worden opgehaald met:

```console
pixi run python scripts/bag.py
```

De scripts delen `processed_data/vbo_buurt/bag_vbo.gpkg` met geselecteerde
woon-VBO's en hun CBS-buurtcode, en
`processed_data/vbo_buurt/cbs_buurt.gpkg` met CBS-buurtpolygonen,
`aantal_woonvbo`, `aantal_inwoners` en `aantal_huishoudens`.

`pixi run inwoners` schrijft daarnaast
`processed_data/inwoners/inwoners.gpkg`. Dit
bestand bevat per woon-VBO de twee inwonersverdelingen
`inwoners_obv_huishoudens` en `inwoners_obv_woonvbo`. Zie
[Inwoners per woon-VBO](../bewerkingen/inwoners-per-vbo.md) voor de betekenis
en beperkingen van deze waarden.

`pixi run auto` schrijft daarnaast `processed_data/autos/autos.gpkg`. Dit bestand
bevat per woon-VBO de gelijkmatig verdeelde waarde `personenautos`. Zie
[Personenauto's per woon-VBO](../bewerkingen/personenautos-per-vbo.md) voor de
betekenis en beperkingen van deze waarde. `pixi run autos` is een gelijkwaardige
alias voor dit script.
