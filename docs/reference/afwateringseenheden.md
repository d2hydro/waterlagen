---
editorial_status: ai
---

# Afwateringseenheden

De functionele uitleg staat bij [Afwateringseenheden](../bewerkte-lagen/afwateringseenheden.md).
Zie [Afwateringseenheden produceren](../produceren/afwateringseenheden.md) voor
de uitvoering, parallel rekenen en logbestanden.

## Brandlagen

`read_brandlagen` combineert de bronnen uit `BrandlagenConfig` in één GeoDataFrame
in het project-CRS. Het resultaat bevat `brandwaarde`, `prioriteit`, geometrie
en de herkomstkolommen `bronbestand`, `bronlaag` en `bron_fid`. Het wordt
gesorteerd op oplopende prioriteit en absolute waarde; bron-FIDs blijven in
een eigen kolom behouden. Lijnen, polygonen en hun multipartvarianten zijn
toegestaan. Z-coördinaten leveren geen brandhoogte; daarvoor dient het attribuut.

Geef `brandlagen=config` mee aan `prepare_watersysteem_rasters`,
`calculate_afwateringseenheden_tiles` of de productie-ingang. De leesfunctie
controleert bronnen, geometrie en attributen; pixelconflicten worden daarna
eenmaal op de echte rekenrasters gecontroleerd. Bronselectie wordt in de
bron-CRS uitgevoerd en de geometrie wordt daarna naar `settings.crs` omgezet.

Het [TOML-schema, de brandregels en een configuratievoorbeeld](../produceren/afwateringseenheden.md#optionele-brandlagen)
staan bij de productie-instructies. Het
[Python-voorbeeld](bewerkte-lagen-produceren.md#afwateringseenheden) toont de bouwstenen.

## Dekking en hergebruik

Bronextents worden in het geheugen gecachet op basis van bestandsversie,
sidecarversies en doel-CRS en op het gevraagde doelgrid gerasteriseerd.
Bij `overwrite=False` worden geldige rasterparen met de actuele coverage-tag
`source_extents_v2` en passende brandmetadata hergebruikt. Ontbrekende of oudere
tags leiden tot regeneratie.

Brandhergebruik houdt rekening met de vaste `burn_depth_m`, het watersysteem,
optionele bronpaden, laagnamen, defaults, project-CRS en brandbeleid. Bronidentiteit
gebruikt bestandspad, grootte en nanoseconde-wijzigingstijd; voor optionele bronnen
wordt ook een aanwezige SQLite-WAL gevolgd. Dit is geen volledige inhoudshash
van grote GeoPackages. Wijzig geen bronbestanden tijdens de verwerking.

De voorbereide `brandlagen.gpkg` heeft een bijbehorend JSON-manifest met de
bron- en grididentiteit. De tegelworkflow controleert dit vóór het starten van
workers; het hele GeoDataFrame wordt niet per worker verstuurd. De losse
rasterfunctie bewaart deze voorbereiding in haar eigen `output_dir`.

Het DEM draagt `waterlagen_burn`; afgeronde tegelberekeningen bewaren daarnaast
`subcatchments_burn.txt`. Alleen een nieuwe DEM-tag is onvoldoende om oude
subcatchments te hergebruiken. Bij veranderde brandinvoer of ontbrekende
metadata worden beide niveaus opnieuw berekend, ook bij `overwrite=False`.
Een mislukte herberekening wordt niet als geldige nieuwe tegelcache aangemerkt.

Met `landsgrens_path` wordt de grenslaag zo nodig naar het raster-CRS omgezet en
per worker gecachet. Bij een gewijzigde landsgrensbron (pad, wijzigingstijd of
bestandsgrootte) worden bestaande rasters en tegelresultaten opnieuw berekend,
ook bij `overwrite=False`. De functies downloaden de grenslaag zelf niet.
Zonder `landsgrens_path` geldt de dekking van de volledige bronextents.
De landsgrenstag bevat ook de maskeringsversie. Uitvoer met de oude maskering,
die een raaklijn ten onrechte als DEM-dekking kon opnemen, wordt eenmalig
opnieuw berekend. Uitvoer zonder landsgrensmasker blijft herbruikbaar als ook
de brandmetadata overeenkomt.

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
