---
editorial_status: ai
---

# Actuele BGT-vlakken voor QGIS

[Landgebruikproductie](landgebruik.md) downloadt en prepareert BGT automatisch.

## Voorbereiden

Download voor losse voorbereiding de landelijke GML-light-ZIP via de
[BGT-bronpagina](../bronlagen/bgt.md#externe-verwijzingen). Bewaar deze bij
standaardopslag als `data/source_data/bgt/bgt-gmllight-nl-nopbp.zip`.

[Download het voorbereidingsscript](../reference/voorbeelden/bereid_bgt_vlakken.py){ .md-button .md-button--primary download="bereid_bgt_vlakken.py" }

Sla het script op in de map met `pixi.toml`. Open daar een terminal en voer uit:

```console
pixi run --locked python bereid_bgt_vlakken.py
```

Open `data/source_data/bgt/bgt.gpkg` in QGIS en zoom naar uw werkgebied. De landelijke ZIP is ook nodig voor een kleine uitsnede. Bij een andere gegevensmap past u `DATA_DIR` aan in het [Python-voorbeeld](../reference/bewerkte-lagen-produceren.md#bgt-vlakken).

## Selectie

De conversie bewaart actuele BGT-vlakken met hun bronattributen, waaronder de laag `bgt_waterdeel`.

??? info "Welke objecten worden geselecteerd?"

    - 17 kandidaatlagen; geen administratieve gebieden, punten of lijnen.
    - Alleen status `bestaand`, zonder `eindRegistratie` en `objectEindTijd`.
    - Bij wegdelen en terreindelen: `geometrie2d`, niet de kruinlijn.
    - Gebogen vlakgrenzen worden omgezet naar rechte segmenten.
    - Lagen zonder actuele vlakken worden overgeslagen.
    - Verkeersborden, sensoren, buurten, openbare ruimten en labels ontbreken.

    De selectie staat in `waterlagen.bgt.prepare.SURFACE_LAYERS`.
    Het argument `workers` bepaalt het aantal gelijktijdige processen.

## Uitvoer en hergebruik

De lagen hebben geometrie `MultiPolygon` en CRS `EPSG:28992`. De ruimtelijke index, het objectaantal en de begrenzing worden opgeslagen. Bekijk `bgt_actuele_vlakken.status.json` en het productielog voor de voortgang of fouten.

??? info "Tijdelijke bestanden"

    De conversie gebruikt een tijdelijke map voor GML en afzonderlijke lagen.
    Na samenvoegen en validatie blijft alleen het gezamenlijke GeoPackage behouden.
    Tijdelijke lagen worden bij normaal afsluiten, ook na een fout, opgeruimd.
    Bij geforceerd stoppen kunnen tijdelijke bestanden achterblijven.

Een bestaand gezamenlijk bestand wordt gecontroleerd en hergebruikt als
`bgt_actuele_vlakken.status.json` alle kandidaatlagen verantwoordt en `Gereed` vermeldt.
Voor hergebruik is de oorspronkelijke ZIP niet nodig.
De losse conversiefunctie vergelijkt geen ZIP-versies; gebruik daar `overwrite=True`
bij een gewijzigde ZIP. Volledige productie vergelijkt de bronidentiteit wel. Zonder afgerond eindbestand begint conversie opnieuw.
