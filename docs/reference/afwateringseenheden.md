# Afwateringseenheden

De DEM-dekking is de vereniging van de volledige rechthoekige rasterextents
(`dataset.bounds`) van alle onderliggende TIFFs in de VRT. Overlap telt eenmaal.
De coverage-bepaling leest uitsluitend georeferentiemetadata, geen pixelwaarden
of NoData-maskers. Ook NoData aan de rand of binnen een TIFF valt binnen dekking
en wordt door de bestaande interpolatie gevuld. NoData buiten alle TIFF-extents
blijft NoData. Met `landsgrens_path` wordt deze dekking verder begrensd tot
Nederland, ook binnen de tegelbuffers.
Na resampling worden cellen buiten dit dekkingsmasker op NoData gezet, vóór
interpolatie. Zo worden randcellen niet onbedoeld als hoogte of donor gebruikt.

Bronextents worden in het geheugen gecachet op basis van bestandsversie,
sidecarversies en doel-CRS en op het gevraagde doelgrid gerasteriseerd.
Bij `overwrite=False` worden geldige rasterparen met de actuele coverage-tag
`source_extents_v2` hergebruikt. Ontbrekende of oudere tags leiden tot regeneratie.

## Parallel rekenen voor Aa en Maas

Het script berekent het beheergebied met `BUFFER_M` als gebiedsbuffer,
`settings.afwateringseenheden_workers` processen, kernen van 10 × 10 km, `TILE_BUFFER_M` als tegelbuffer
en een resolutie van 2 m.
Iedere tegel gebruikt seed 12345. Meer workers vragen meer werkgeheugen.
Het aantal workers is instelbaar via `.env` (standaard 35):

```dotenv
AFWATERINGSEENHEDEN_WORKERS=35
```

Randproblemen leiden niet tot herberekening met een grotere buffer;
na afloop worden gaten waar mogelijk aangevuld vanuit buurtegels.

Start vanuit de repository in een terminal:

```powershell
pixi run --environment afwateringseenheden python scripts/afwateringseenheden_aa_en_maas.py
```

Elke start maakt een nieuwe map
`<datastore.afwateringseenheden_path>/aa_en_maas_<datum-tijd>/` met
`afwateringseenheden.gpkg`, het hoofdlog en `tiles/<tegel-id>/` met rasters,
tegelpolygonen en `workflow.log`. Eerdere runs blijven behouden. De AHN-selectie
wordt per run gecontroleerd; geldige tegels worden hergebruikt en ontbrekende
tegels gedownload. HyDAMO-brondata wordt hergebruikt, maar het watersysteem
wordt voor het huidige gebied opnieuw voorbereid in `watersysteem.gpkg` in de runmap.

De totale verwerkingstijd per tegel staat in `afwateringseenheden.log` en, bij
parallel rekenen, in `tiles/<tegel-id>/workflow.log`. Deze tijd omvat
rastervoorbereiding, afwatering en uitvoer.
Wachttijd in de pool en het gezamenlijke samenvoegen vallen erbuiten. Bij
hergebruik meet de timer alleen het controleren en verwerken van de bestaande
tegeluitvoer. In Python staat de tijd in `calculation_duration_seconds` per tegel.

### AHN binnen de Nederlandse landsgrens

Het script gebruikt uitsluitend AHN als hoogtebron. Het downloadt bestuurlijke
gebieden (standaard jaargang 2026) met `overwrite=False` en geeft deze bron als
`landsgrens_path` door aan de tegelberekening. Bestaande bronbestanden worden
hergebruikt. De laag `landgebied` bepaalt de Nederlandse landsgrens.

Elke tegel, inclusief rekenbuffer, wordt binnen de AHN-bronextents volledig
dichtgeinterpoleerd voor zover de celmiddens binnen Nederland liggen. Ook gaten
aan de rand van een brontegel blijven vulbaar. Buiten de landsgrens worden
hoogtes op NoData gezet voordat de interpolatie begint; deze cellen worden niet
gevuld en dienen niet als donor. Als er binnen de dekking geen enkele bruikbare
hoogte is om aanwezige gaten te vullen, stopt de verwerking met een foutmelding.

De grenslaag wordt zo nodig naar het raster-CRS omgezet en per worker gecachet.
Bij een gewijzigde landsgrensbron (pad, wijzigingstijd of bestandsgrootte) worden
bestaande rasters en tegelresultaten opnieuw berekend, ook bij `overwrite=False`.
De functies `calculate_afwateringseenheden_tiles` en
`prepare_watersysteem_rasters` downloaden de grenslaag zelf niet. Zonder
`landsgrens_path` behouden ze hun bestaande dekking op basis van bronextents.

De workers rekenen in afzonderlijke `spawn`-processen; het hoofdproces voegt
de resultaten samen. De functie zelf gebruikt standaard één worker. Start
parallelle berekeningen vanuit een script met een `__main__`-guard.

## Opschonen en aanvullen bij het samenvoegen

Losse lijn- en puntresten worden verwijderd. Gaten worden gevuld vanuit
bestaande buurpolygonen, zonder nieuwe LDD. Polygonen die hun buitenste
rekenrand raken vallen af. De buur met de meeste dekking krijgt voorrang;
bij gelijke dekking volgen de grootste randafstand en daarna het tegel-ID.
Alleen lege ruimte wordt aangevuld: bestaande toewijzingen blijven behouden.
Zonder bruikbare buur blijft een gat open, ook bij 5 km buffer.

De GeoPackage bevat alleen `afvoergebiedaanvoergebied`, met Polygon- en
MultiPolygon-geometrie. In Python zijn aanvullingen en resterende gaten
beschikbaar als `result.gap_additions` en `result.remaining_gaps`.
`boundary_issue_tile_ids` betreft de randproblemen vóór het aanvullen.

Bij `overwrite=False` kan bestaande tegeluitvoer worden hergebruikt.
Daarvoor is ook `subcatchments.tif` nodig: dit bepaalt de werkelijke buffer;
CRS en resolutie moeten overeenkomen. Het opgegeven samengevoegde eindbestand
wordt na succes wel vervangen. Kies een nieuw eindpad om de vorige versie te bewaren.

::: waterlagen.afwateringseenheden

::: waterlagen.afwateringseenheden.dem.prepare_ahn_dgm1_dem
