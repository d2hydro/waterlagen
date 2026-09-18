# Afwateringseenheden

De functionele uitleg staat bij [Afwateringseenheden](../bewerkingen/afwateringseenheden.md).
Zie [Afwateringseenheden produceren](../produceren/afwateringseenheden.md) voor
de uitvoering, parallel rekenen en logbestanden.

## Dekking en hergebruik

Bronextents worden in het geheugen gecachet op basis van bestandsversie,
sidecarversies en doel-CRS en op het gevraagde doelgrid gerasteriseerd.
Bij `overwrite=False` worden geldige rasterparen met de actuele coverage-tag
`source_extents_v2` hergebruikt. Ontbrekende of oudere tags leiden tot regeneratie.

Met `landsgrens_path` wordt de grenslaag zo nodig naar het raster-CRS omgezet en
per worker gecachet. Bij een gewijzigde landsgrensbron (pad, wijzigingstijd of
bestandsgrootte) worden bestaande rasters en tegelresultaten opnieuw berekend,
ook bij `overwrite=False`. De functies downloaden de grenslaag zelf niet.
Zonder `landsgrens_path` geldt de dekking van de volledige bronextents.
De landsgrenstag bevat ook de maskeringsversie. Uitvoer met de oude maskering,
die een raaklijn ten onrechte als DEM-dekking kon opnemen, wordt eenmalig
opnieuw berekend. Uitvoer zonder landsgrensmasker blijft herbruikbaar.

Voor hergebruik van tegeluitvoer is ook `subcatchments.tif` nodig: dit bepaalt
de werkelijke buffer; CRS en resolutie moeten overeenkomen. Het opgegeven
samengevoegde eindbestand wordt na succes wel vervangen. Kies een nieuw eindpad
om de vorige versie te bewaren.

## Tegelresultaten

`gap_additions` bevat aanvullingen uit buurtegels en `remaining_gaps` de
resterende gaten. `boundary_issue_tile_ids` betreft randproblemen voordat het
resultaat is aangevuld. `calculation_duration_seconds` geeft de verwerkingstijd
per tegel, zonder wachttijd in de pool of het gezamenlijke samenvoegen.

`skipped_tile_ids` bevat tegels zonder segmentcellen op geldige DEM-hoogtes.
Hiervoor worden zowel het segmentraster als het NoData-masker en de eindige
hoogtewaarden van het DEM gecontroleerd. Voor overgeslagen tegels worden geen
LDD- of subcatchmentbestanden gemaakt; de voorbereide rasters blijven behouden.

`tiles.gpkg` wordt in de opgegeven `output_dir` geschreven. De laag `tiles`
bevat de geselecteerde kerntiles en een `tile_id`-kolom met de namen van de
bijbehorende tegelmappen.

De functie gebruikt standaard een worker. Parallelle berekeningen gebruiken
afzonderlijke `spawn`-processen en vereisen een script met een `__main__`-guard.

::: waterlagen.afwateringseenheden

::: waterlagen.afwateringseenheden.dem.prepare_ahn_dgm1_dem

## Productie voor een waterschap

Voor uitvoering vanuit de terminal, zie
[Afwateringseenheden produceren](../produceren/afwateringseenheden.md).

::: waterlagen.afwateringseenheden.production.ProductionConfig

::: waterlagen.afwateringseenheden.production.produce_afwateringseenheden
