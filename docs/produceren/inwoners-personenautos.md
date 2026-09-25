# Inwoners en personenauto's voorbereiden

Installeer eerst het [productiepakket](installatie.md). Voer de opdrachten
hieronder uit vanuit de projectfolder met `pixi.toml` en `pixi.lock`.

De workflows voor inwoners en personenauto's starten met dezelfde bron- en
tussenproductstappen. Beide downloaden de CBS-bronnen alleen wanneer die nog
niet in de DataStore staan en bouwen alleen nieuwe VBO-buurtbestanden wanneer
die nog niet bestaan.

Voer een van de afzonderlijke workflows uit met Pixi:

```console
pixi run --locked inwoners --run-id voorbeeld
pixi run --locked auto --run-id voorbeeld
```

Vergelijk de CBS-totalen met de sommen van de verdeelde waarden met:

```console
pixi run --locked statistiek_inwoners_autos --inwoners-path data/processed_data/inwoners/nederland/voorbeeld/inwoners.gpkg --autos-path data/processed_data/autos/nederland/voorbeeld/autos.gpkg
```

Voer de statistiekcontrole uit nadat beide producties klaar zijn. Pas de paden
aan als u een andere opslaglocatie of run-ID gebruikt. Zonder expliciete
invoerbestanden gebruikt deze controle nog de oude vaste `DataStore`-paden.
De taken `inwoners` en `auto` downloaden vooraf automatisch de landelijke
BAG-light GeoPackage met `scripts/bag.py`, of hergebruiken de bestaande download.
U kunt BAG-light ook afzonderlijk ophalen:

```console
pixi run --locked bag
```

De scripts voeren een landelijke productie uit; houd rekening met grote downloads,
schijfruimte en rekentijd. De onderstaande uitvoerpaden liggen onder `data`,
tenzij u de [opslaglocatie](configuratie.md) hebt aangepast.

De scripts delen `processed_data/vbo_buurt/bag_vbo.gpkg` met geselecteerde
woon-VBO's en hun CBS-buurtcode, en
`processed_data/vbo_buurt/cbs_buurt.gpkg` met CBS-buurtpolygonen,
`aantal_woonvbo`, `aantal_inwoners`, `aantal_huishoudens` en
`personenautos_totaal`.

`pixi run --locked inwoners` schrijft daarnaast
`processed_data/inwoners/nederland/<run-id>/inwoners.gpkg`. Dit
bestand bevat per woon-VBO de twee inwonersverdelingen
`inwoners_obv_huishoudens` en `inwoners_obv_woonvbo`. Zie
[Inwoners per woon-VBO](../bewerkingen/inwoners-per-vbo.md) voor de betekenis
en beperkingen van deze waarden.

Voor een aanvullend cloudgericht GeoParquet-bestand zet je bovenin
`scripts/inwoners.py` de optie `WRITE_GEOPARQUET = True`. De workflow schrijft
dan ook `inwoners.parquet` in dezelfde runmap.

`pixi run --locked auto` schrijft daarnaast `processed_data/autos/nederland/<run-id>/autos.gpkg`. Dit bestand
bevat per woon-VBO de gelijkmatig verdeelde waarde `personenautos`. Zie
[Personenauto's per woon-VBO](../bewerkingen/personenautos-per-vbo.md) voor de
betekenis en beperkingen van deze waarde. `pixi run --locked autos` is een gelijkwaardige
alias voor dit script.

Voor de auto-uitvoer zet je op dezelfde manier `WRITE_GEOPARQUET = True` in
`scripts/auto.py`. Dan wordt ook `autos.parquet` in dezelfde runmap
geschreven.

Zonder `--run-id` krijgt iedere productie een nieuwe UTC-tijdstempel als run-ID.
Een bestaande naam vereist `--resume` voor hergebruik, of `--overwrite` voor
herberekening met dezelfde instellingen en bronnen. Beide opties gelden alleen
voor productie-uitvoer; de gedeelde VBO-buurtbestanden blijven herbruikbaar.
Bij gewijzigde invoer kiest u een nieuwe run-ID. De productielogs (`auto.log`
of `inwoners.log`) en `run.json` staan in de runmap. Zie de gezamenlijke
[conventie voor productiemappen](configuratie.md#productiemappen).
