---
editorial_status: ai
---

# Afwateringseenheden

De productie bereidt altijd het gezamenlijke waternet voor, ook zonder
aanvullende brandlagen. `BrandlagenConfig` en de TOML bevatten geen
`waternet`-schakelaar. Verwijder deze sleutel uit bestaande TOML-bestanden.

De functionele uitleg staat bij [Afwateringseenheden](../bewerkte-lagen/afwateringseenheden.md).
Zie [Afwateringseenheden produceren](../produceren/afwateringseenheden.md) voor
de uitvoering, parallel rekenen en logbestanden.

## Bronselectie en afwateringsdoelen

`read_watersysteem_sources` levert afzonderlijke primaire en secundaire
brandcontext (`primary`, `secondary`), primaire doelen (`targets`) en
deelnemende kunstwerken (`points`). Gebruik `targets` en `points` voor
`prepare_watersysteem`, samen met `hydroobject_primair=sources.primary` en
`duikersifonhevel=sources.culverts`; geef de volledige `primary` en `secondary` aan
`write_watersysteem`. Die schrijft expliciete categorielagen en classificeert
secundaire groepen gezamenlijk tegen de volledige primaire brongeometrie.
Zo hangt de brandselectie niet af van de doelmodus.

Geef `missing_category` als `hydroobject_zonder_categorie` aan
`write_watersysteem` mee om de uitgesloten GKW-lijnen zonder categorie zichtbaar
te houden. Ze doen niet mee aan branden, doelen of de secundaire verbindingstoets.

De oorspronkelijke identifiers blijven behouden naast `bronbestand`, `bronlaag`
en `bron_fid`. Samengestelde `bron_id`-waarden bevatten bestand, laag, FID en
het oorspronkelijke bron-ID, zodat FIDs en globalids tussen bronnen mogen overlappen.

::: waterlagen.afwateringseenheden.read_watersysteem_sources

::: waterlagen.afwateringseenheden.WatersysteemSources

## Duikervoorbereiding

`read_duikersifonhevel` leest volledige brongeometrieën in het project-CRS,
met bronbestand, laag en oorspronkelijke FID. Onbruikbare geselecteerde
geometrieën worden behouden voor controle. Zonder ruimtelijke selectie worden
ook geometrieën zonder locatie gelezen; een ruimtelijke selectie kan objecten
zonder locatie niet aan een rekencontext toewijzen.

`prepare_watersysteem` koppelt duikers eenmaal aan de volledige primaire
context, vóór de doelafhankelijke voorbereiding. Zonder `duikersifonhevel`
blijven bestaande lagere aanroepen werken. Met duikerinvoer geldt de
uitsluiting altijd, ook met `max_aansluitlengte=None`.

Kandidaten worden bepaald met de inclusieve `duiker_tolerance` per uiteinde.
Routes volgen bestaande gedeelde bronlijneindpunten en moeten in de
projectierichting langs de duiker voortgaan. Kruisingen zonder bestaand
knooppunt zijn geen verbinding. Bij meerdere routes bepaalt de kleinste
Hausdorff-afstand tot de duikergeometrie de kandidaat; gelijke scores blijven
ambigu. Beheerder, FID en netwerkafstand geven geen doorslag. Er wordt geen
bufferstrook voor het hele duikertraject gebruikt.

Dit is een geometrische koppeling, geen bewijs van een hydraulische relatie.
Niet-monotone routes, onbruikbare of gesloten duikerlijnen en niet te
onderscheiden routes gaan naar controle. Aaneengesloten multipartduikers
worden samengevoegd voor de koppeling; de originele controlegeometrie blijft
behouden. Om onbegrensd zoeken in complexe netwerken te vermijden worden
meer dan 128 kandidaattrajecten of 10.000 zoekstappen als ambigu gemeld.

`WatersysteemResult` bevat de volledige primaire bron, de geknipte primaire
delen, de volledige doelsegmentlaag en `duiker_controle`. De schrijver bewaart
de volledige bron en geknipte context in `intern/watersysteem.gpkg`, lagen
`hydroobject_primair_bron` en `hydroobject_primair_delen`. De geschikte
branddelen blijven in `watersysteem.gpkg`, laag `hydroobject_primair`.
De secundaire toets blijft de volledige bron gebruiken.
De duikercontrole staat alleen in `controle_path` (standaard `controle.gpkg`
naast het snapshot, laag `duikersifonhevel`). Dit bestand bevat ook eventuele
bronobjecten zonder categorie. Het watersysteem bevat vijf gebruikslagen.

De segmentkolommen `brandgeschikt` en `doelgeschikt` hebben afzonderlijke
betekenissen. `duiker_ids` identificeert overlappende duikers;
`aansluit_duiker_ids` identificeert directe aansluitingen. Lengteclassificatie
vindt vóór `max_length` plaats en wordt doorgegeven aan de deelsegmenten.
Filtering van het doelraster behoudt de opgeslagen FIDs voor de terugkoppeling
naar de numerieke `segment_id`, met `segment_key` als technische sleutel;
gaten worden niet opgevuld.

Voorbereiding en schrijven controleren inhoudelijke invoeridentiteiten,
inclusief controleobjecten, doelmodus en instellingen. Bronlezers voegen ook
bestandsidentiteiten en SQLite-WAL toe. Een afwijkende duikersnapshot wordt
ook met `overwrite=False` vernieuwd; een gewijzigd snapshot maakt via de
bestaande brandidentiteit zowel rasters als tegelresultaten ongeldig. Ontbrekende
controle-uitvoer wordt bij schrijven hersteld. Het uitschakelen van duikerinvoer
maakt een eerder met duikers voorbereid snapshot eveneens ongeldig.
De technische controle staat in `intern/watersysteem.gpkg.json`, gekoppeld aan
de checksum van de uitvoer. Bij ontbrekende of afwijkende metadata wordt het
watersysteem opnieuw geschreven. `watersysteem.gpkg` bevat geen tabel
`waterlagen_duikers` meer.

Zie het [uitvoerbare voorbeeld](bewerkte-lagen-produceren.md#afwateringseenheden)
en de [controle-instructies](../produceren/afwateringseenheden.md#controle-in-qgis).

::: waterlagen.afwateringseenheden.read_duikersifonhevel

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
