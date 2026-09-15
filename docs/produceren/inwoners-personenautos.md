# Inwoners en personenauto's voorbereiden

De workflows voor inwoners en personenauto's starten voorlopig met dezelfde
bron- en tussenproductstappen. Beide downloaden de CBS-bronnen alleen wanneer
die nog niet in de DataStore staan en bouwen alleen nieuwe VBO-buurtbestanden
wanneer die nog niet bestaan.

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
`aantal_woonvbo`, `aantal_inwoners` en `aantal_huishoudens`. Er worden nog geen
inwoners- of personenautowaarden per VBO berekend.
