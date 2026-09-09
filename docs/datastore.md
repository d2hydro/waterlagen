## Algemeen
De datastore geeft structuur aan het opslaan van downloads en bewerkingen. Standaard wordt de map `data` in de repository-root gebruikt. De mappen `source_data` en `processed_data` zijn sub-mappen onder de `data` map.


Optioneel kun je een bestand `.datastore` in de repository-root of huidige werk-directory maken met daarin `DATA_DIR=pad\naar\mijn\data_store`. Als beide bestanden bestaan, heeft het bestand in de huidige werk-directory voorrang. Op dezelfde manier kun je `source_data` hierin zetten met `SOURCE_DATA=pad\naar\mijn\brongegevens` evenals `processed_data` met `PROCESSED_DATA=pad\naar\mijn\bewerkte\gegevens`.

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
Voor de GKW HYDAMO-download is `datastore.hydamo_dir` de standaardmap onder
`source_data/hydamo`.

Administratieve gebiedsbronnen staan onder
`datastore.administratieve_gebieden_dir`, oftewel
`source_data/administratieve_gebieden`.

## Gebruik
Zie de [code referentie](reference/datastore.md). Mocht u bijvoorbeeld willen weten waar de data_dir staat:

```python
from waterlagen import datastore

print(datastore.data_dir)
```
