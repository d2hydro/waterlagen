# Afwateringseenheden

De DEM-dekking is de vereniging van de volledige rechthoekige rasterextents
(`dataset.bounds`) van alle onderliggende TIFFs in de VRT. Overlap telt eenmaal.
De coverage-bepaling leest uitsluitend georeferentiemetadata, geen pixelwaarden
of NoData-maskers. Ook NoData aan de rand of binnen een TIFF valt binnen dekking
en wordt door de bestaande interpolatie gevuld. NoData buiten alle TIFF-extents
blijft NoData.

Bronextents worden in het geheugen gecachet op basis van bestandsversie,
sidecarversies en doel-CRS en op het gevraagde doelgrid gerasteriseerd.
Bij `overwrite=False` worden geldige rasterparen met de actuele coverage-tag
`source_extents_v1` hergebruikt. Ontbrekende of oudere tags leiden tot regeneratie.

## Parallel rekenen voor Aa en Maas

Het script berekent het beheergebied plus 5 km met tien workers, kernen van
10 × 10 km, een vaste tegelbuffer van 5 km en een resolutie van 2 m.
Iedere tegel gebruikt seed 12345. Meer workers vragen meer werkgeheugen.

Start vanuit de repository in een terminal:

```powershell
pixi run --environment afwateringseenheden python scripts/afwateringseenheden_aa_en_maas.py
```

Elke start maakt een nieuwe map
`<datastore.afwateringseenheden_path>/aa_en_maas_<datum-tijd>/` met
`afwateringseenheden.gpkg`, het hoofdlog en `tiles/<tegel-id>/` met rasters,
tegelpolygonen en `workflow.log`. Eerdere runs blijven behouden; bestaande
AHN- en watersysteembronnen worden hergebruikt.

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
