## Algemeen
De datastore geeft structuur aan het opslaan van downloads en bewerkingen. Standaard wordt een map `data` aangemaakt relatief tot de huidige werk-map. De mappen `source_data` en `processed_data` zijn sub-mappen onder de `data` map.


 Optioneel kun je een bestand `.datastore` in de huidige werk-directory maken met daarin `DATA_DIR=pad\naar\mijn\data_store`. Op dezelfde manier kun je `source_data` hierin zetten met `SOURCE_DATA=pad\naar\mijn\brongegevens` even als `processed_data` met `PROCESSED_DATA=pad\naar\mijn\bewerkte\gegevens`.

De DataStore ziet er als volgt uit:

```
data
├── processed_data
│   └── dtm_05
│       ├── dtm_05.vrt
│       └── ...
├── source_data
│   ├── ahn
│   │   ├── dtm_05.vrt
│   │   └── ...
│   ├── bag
│   │   └── bag-light.gpkg
│   └── bgt
│       └── ...
└── logs
    └── ...
```
## Gebruik
Zie de [code referentie](reference/datastore.md). Mocht u bijvoorbeeld willen weten waar de data_dir staat:

```python
from waterlagen import datastore

print(datastore.data_dir)
```
