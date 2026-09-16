# Afwateringseenheden

De DEM-dekking is de vereniging van de volledige rechthoekige rasterextents
(`dataset.bounds`) van alle onderliggende TIFFs in de VRT. Overlap telt eenmaal.
De coverage-bepaling leest uitsluitend georeferentiemetadata, geen pixelwaarden
of NoData-maskers. Ook NoData aan de rand of binnen een TIFF valt binnen dekking
en wordt door de bestaande interpolatie gevuld. NoData buiten alle TIFF-extents
blijft NoData.
Na resampling worden cellen buiten dit dekkingsmasker op NoData gezet, vóór
interpolatie. Zo worden randcellen niet onbedoeld als hoogte of donor gebruikt.

Bronextents worden in het geheugen gecachet op basis van bestandsversie,
sidecarversies en doel-CRS en op het gevraagde doelgrid gerasteriseerd.
Bij `overwrite=False` worden geldige rasterparen met de actuele coverage-tag
`source_extents_v2` hergebruikt. Ontbrekende of oudere tags leiden tot regeneratie.

## Parallel rekenen voor Aa en Maas

Het script berekent het beheergebied met `BUFFER_M` als gebiedsbuffer,
`WORKERS` processen, kernen van 10 × 10 km, `TILE_BUFFER_M` als tegelbuffer
en een resolutie van 2 m.
Iedere tegel gebruikt seed 12345. Meer workers vragen meer werkgeheugen.

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
rastervoorbereiding, afwatering en uitvoer, inclusief eventuele herhaalpogingen.
Wachttijd in de pool en het gezamenlijke samenvoegen vallen erbuiten. Bij
hergebruik meet de timer alleen het controleren en verwerken van de bestaande
tegeluitvoer. In Python staat de tijd in `calculation_duration_seconds` per tegel.

### Duits DEM langs de grens

Het script combineert AHN met de gedownloade tegels in `source_data/dgm1_nrw`.
DGM1 wordt van UTM32/DHHN2016 naar RD/NAP omgerekend, op een 1m-grid en met
dezelfde hoogteopslag als AHN (momenteel centimeters). De omzetting gebruikt
de [BKG- en NSGI-correctiegrids](https://cdn.proj.org/): `de_bkg_gcg2016.tif`,
`nl_nsgi_nlgeo2018.tif` en `nl_nsgi_rdtrans2018.tif`.
Ontbrekende grids worden eenmalig naar `source_data/proj_grids` gedownload.
Buiten het geldige bereik van deze grids stopt de omzetting; er is geen
benaderende terugval of vaste hoogtecorrectie.

Geldig AHN heeft voorrang. DGM1 vult ontbrekend AHN aan vóór interpolatie,
ook binnen rekenbuffers. Dit gebruikt de databeschikbaarheid, **geen landsgrensmasker**.
De oorspronkelijke interpolatie voor resterende NoData binnen bronextents blijft
bestaan; ontbrekende Duitse tegels worden hiermee niet automatisch gedownload.

Omgerekende tegels staan in `processed_data/dgm1_nrw_rdnap` en worden hergebruikt.
Bij gewijzigde bron- of conversiegegevens vraagt het script om een nieuwe cachemap.
Elke run krijgt een eigen `ahn_dgm1_rdnap.vrt`; downloads en eerdere runs blijven
behouden. Een reeds berekende LDD verandert niet: het script start een nieuwe run.

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
