# Actuele BGT-vlakken voor QGIS

[Landgebruikproductie](landgebruik.md) downloadt en prepareert BGT automatisch.
Voor losse conversie van een bestaande [BGT GML Light-ZIP](../bronnen/bgt.md)
gebruikt u de [Python-functie](../reference/gebruik.md#losse-bronnen-en-bewerkingen)
`waterlagen.bgt.productie.main`. Deze conversiefunctie downloadt zelf niets.

## Selectie

- 17 kandidaatlagen; geen administratieve gebieden, punten of lijnen.
- Alleen status `bestaand`, zonder `eindRegistratie` en `objectEindTijd`.
- Bij wegdelen en terreindelen: `geometrie2d`, niet de kruinlijn.
- Gebogen vlakgrenzen worden omgezet naar rechte segmenten.
- Lagen zonder actuele vlakken worden overgeslagen.
- Verkeersborden, sensoren, buurten, openbare ruimten en labels ontbreken.

De selectie staat in `waterlagen.bgt.prepare.SURFACE_LAYERS`.
Het argument `workers` bepaalt het aantal gelijktijdige processen.

## Uitvoer en hergebruik

Uitvoer: `source_data/bgt/bgt.gpkg`.
Elke laag heeft `MultiPolygon`, CRS `EPSG:28992`, een ruimtelijke index,
opgeslagen objectaantal en laagbegrenzing. Bronattributen blijven behouden.
`bgt_actuele_vlakken.status.json` en het productielog vermelden voortgang en fouten.

Open het GeoPackage in QGIS en zoom in op uw werkgebied. De index versnelt
ruimtelijke selecties; het tekenen van heel Nederland kan lang duren.

De conversie gebruikt een tijdelijke map voor GML en afzonderlijke lagen.
Na samenvoegen en validatie blijft alleen het gezamenlijke GeoPackage behouden.
Tijdelijke lagen worden bij normaal afsluiten, ook na een fout, opgeruimd.
Bij geforceerd stoppen kunnen tijdelijke bestanden achterblijven.

Een bestaand gezamenlijk bestand wordt gecontroleerd en hergebruikt als
`bgt_actuele_vlakken.status.json` alle kandidaatlagen verantwoordt en `Gereed` vermeldt.
Voor hergebruik is de oorspronkelijke ZIP niet nodig.
De losse conversiefunctie vergelijkt geen ZIP-versies; gebruik daar `overwrite=True`
bij een gewijzigde ZIP. Volledige productie vergelijkt de bronidentiteit wel. Zonder afgerond eindbestand begint conversie opnieuw.

De landelijke landgebruiksberekening gebruikt standaard dit `bgt.gpkg`.
