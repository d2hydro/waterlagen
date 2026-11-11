# Referentie parallelle routes

Kleine geometrieselectie uit de lokale HyDAMO-bron
`D:/data/datastore_test/source_data/hydamo/hydamo.gpkg`, laagmetadata 6 november
2026. Selectievenster EPSG:28992: `(179680,373810,179850,373925)`.
Volledige brongeometrieën zijn behouden, ook buiten het venster. Alleen
`globalid`, categorie en geometrie zijn opgenomen. GeoJSON heeft hier expliciet
EPSG:28992; dit zijn geen WGS84-coördinaten.

De zes referentiehydroobjecten staan op twee parallelle lussen met een gedeelde
knoop. De twee oostelijke routes omvatten ieder twee bronobjecten. De selectie
bevat ook buitenwaterlopen en een niet verbonden kruising voor regressietests.
De tests voeren geen externe downloads uit.

SHA-256 van de fixturebestanden:

- `duikersifonhevel.geojson`: `ebc6382ce296d1321c83f6e7ef4db94ff13f5f30c6fbd3b7e651457347ffde3c`
- `hydroobject.geojson`: `80972da023505889652af420601193cde9a923ea8fc9f7ad73d2cdbeebc58eb5`
- `stuw.geojson`: `5434ca91666c9e0d3c1e4fb2a68472d73d22f46a14eb1cbca8620a56f033cb43`
