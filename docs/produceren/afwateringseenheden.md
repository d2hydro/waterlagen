---
editorial_status: ai
---

# Afwateringseenheden produceren

Deze productie ondersteunt Nederland, een waterschapscode en gedeelde gebieden
zoals Alkmaar. Volg eerst [Installatie](installatie.md); het releasepakket bevat
PCRaster. Vanuit de repository gebruikt u de omgeving `afwateringseenheden`.

## Starten

```console
pixi run --locked afwateringseenheden --area alkmaar --workers 2
pixi run --locked afwateringseenheden --waterbeheercode 38 --workers 2
```

Zonder gebiedsoptie wordt **Nederland** verwerkt. Een onbekende waterschapscode
geeft een fout voordat AHN en HYDAMO worden opgehaald. Kies `--workers 1` bij
weinig werkgeheugen. De overige [gedeelde CLI-opties](cli.md) regelen opslag,
bronvernieuwing, offline gebruik en hervatten.

## Workflow

### Eigen gebied met brandlagen

[Download het PowerShell-voorbeeld](voorbeelden/afwateringseenheden_issue63.ps1).
Het selecteert 1 × 1 km rond RD-punt `(184785, 392554)` uit issue 63.
Gebruik hiervoor `settings.crs = EPSG:28992`. Zie de
[gedeelde gebiedsuitleg](cli.md#eigen-rechthoekig-gebied).

1. Maak de brandlagen in QGIS en sla ze op in een GeoPackage.
2. Wijs de bestanden en lagen aan in de [brandlagen-TOML](#toml-configuratie).
3. Start vanuit de repositoryroot:

   ```powershell
   .\docs\produceren\voorbeelden\afwateringseenheden_issue63.ps1 -BrandlagenConfig '.\invoer\brandlagen.toml'
   ```

4. Open de gelogde resultaatmap en laad de uitvoer in QGIS.
5. Pas zo nodig de brandlagen aan, sla ze op en start opnieuw.

De vier grenzen en het configuratiepad zijn parameters bovenaan het script.
Een relatief configuratiepad geldt vanaf de werkdirectory waarin u het script
start. GeoPackage-paden in de TOML blijven relatief aan het TOML-bestand.
Het script voert de productie vanuit de repositoryroot uit en geeft fouten door.

Iedere uitvoering krijgt een nieuwe UTC-runmap. Na wijzigingen aan brandlagen
is een nieuwe run nodig, ook bij `--overwrite`. Gebruik `--resume` alleen voor
een onderbroken run met dezelfde invoer. Bewerk invoer niet tijdens een run.
Ook zonder optionele brandlagen blijft de vaste HYDAMO-inbranding actief.

### Verwerking

1. Het gebied selecteert volledige tegelkernen van 10 x 10 km.
2. GKW HYDAMO en de gepubliceerde Rijkswaterenbron worden opgehaald of lokaal
   hergebruikt. Een eventuele eigen levering en de geselecteerde bronobjecten
   worden gecontroleerd vóór de AHN-voorbereiding.
3. Bronnen worden geselecteerd voor volledige tegelkernen en rechthoekige
   buffers. Hun geometrie blijft volledig behouden. De AHN-selectie dekt
   dezelfde rekencontext. Doelen en brandcontext worden afzonderlijk gekozen.
4. De productie berekent de tegels en voegt de bruikbare resultaten samen.
   De gebiedsgrens knipt het resultaat niet af.

De tegelbuffer is 2000 m, de rasterresolutie 2 m, de inbranddiepte voor
secundaire waterlopen 100 m en de maximale opvuldiepte 50 m. De vaste seed is
12345. De landsgrens begrenst de AHN-interpolatie tot Nederland. Dit staat los
van de gekozen gebiedsgrens als invoerselectie.
De betekenis en beperkingen staan bij
[Afwateringseenheden](../bewerkte-lagen/afwateringseenheden.md).

## Doelmodi en bronnen

| Selectie | Primaire afwateringsdoelen | Alleen brandcontext |
| --- | --- | --- |
| Waterschapscode, standaard | Eigen waterschap | Overige waterschappen en RWS |
| Waterschapscode met `--overige-waterschappen` | Eigen en overige waterschappen | RWS |
| Geen waterschapscode | Alle geselecteerde waterschappen en RWS | Geen afzonderlijke beheerdergroep |

De nieuwe standaard bij een waterschapscode verschilt van de eerdere productie,
die alle ruimtelijk geselecteerde GKW-beheerders als doelen gebruikte.
Zonder waterschapscode leveren Rijkswateren ook in een uitsnede zoals
`--area alkmaar` doelen. De vlag verandert de brandselectie en het gebrande DEM
niet, maar wel de segmenten en mogelijke doeltoekenning. Secundaire lijnen
leveren nooit zelf doelen. Alleen kunstwerken van deelnemende beheerders
worden gebruikt bij de bestaande segmentvoorbereiding.

De [Rijkswaterenbron](../bronlagen/rijkswateren.md) levert alle RWS-lijnen.
GKW-hydroobjecten met code `80` worden uitgesloten, ook uit de brandcontext.
GKW-gemalen en -stuwen van code `80` blijven beschikbaar wanneer RWS doelen
levert. Ontbrekende RWS-lijnen worden niet uit GKW aangevuld.
`--rijkswateren-url` stelt een andere publieke share of directe GeoPackage-URL in.
Publicatie blijft handmatig; lokale opslag is `source_data/hydamo/rws_hydamo.gpkg`.

```console
pixi run --environment afwateringseenheden afwateringseenheden --waterbeheercode 38 --run-id aa-maas-eigen
pixi run --environment afwateringseenheden afwateringseenheden --waterbeheercode 38 --overige-waterschappen --run-id aa-maas-samen
pixi run --environment afwateringseenheden afwateringseenheden --waterbeheercode 38 --eigen-hydamo eigen.gpkg --run-id eigen-bron
```

### Eigen levering

`--eigen-hydamo` vervangt alle GKW-objecten van de gekozen beheerder, ook in
de brandcontext. De lagen `hydroobject`, `gemaal`, `stuw` en `duikersifonhevel` zijn verplicht;
kunstwerklagen mogen leeg zijn. Alle objecten moeten een geldige `nen3610id`
van de gekozen beheerder hebben (`NL.WBHCODE.<code>.<rest>`). Ook identifiers
buiten de ruimtelijke selectie worden gecontroleerd. Selecteer een levering
met meerdere beheerders vooraf. Er is geen fallback naar GKW bij brongaten.
GKW blijft nodig voor de omgeving. Beide beheerderopties vereisen een
waterschapscode; in Python heten ze `eigen_hydamo` en `overige_waterschappen`.
Ook een lege eigen duikerlaag vervangt alle GKW-duikers van die beheerder;
er wordt niets uit GKW aangevuld. Leveringen zonder deze vierde laag geven
vóór AHN-voorbereiding een fout.

Beide categorievelden `categorieoppwaterlichaam` en `categorieoppervlaktewater`
worden herkend. Bekende waarden zijn `primair`, `secundair`, `tertiair` en
`overig`; tertiaire lijnen doen alleen mee met `waternet = true`. Overige lijnen worden niet gebruikt. GKW-lijnen zonder
categorie blijven buiten branden en doelen en worden met een waarschuwing in
`hydroobject_zonder_categorie` bewaard, inclusief oorspronkelijke identificaties,
bronbestand, laag en FID. Er wordt geen categorie geraden. Onbekende ingevulde
waarden, ontbrekende categorieën in een eigen levering of RWS-bron,
tegenstrijdige kolommen en ontbrekende CRS-definities geven een fout.
Een bekend afwijkend CRS wordt expliciet naar het project-CRS getransformeerd.

### Gezamenlijke secundaire verbindingstoets

Onderstaande geometrische toets geldt zonder `waternet = true`. Het
[gezamenlijke waternet](#gezamenlijk-waternet) gebruikt rasterverbindingen.

Alle geselecteerde secundaire lijnen worden gezamenlijk gegroepeerd met een
tolerantie van 2 m. Een groep wordt gebrand zodra één lid binnen 2 m van een
geselecteerde primaire lijn ligt. Een keten over beheerdergrenzen of een
aansluiting uitsluitend op RWS kan dus voldoende zijn. De volledige
lijngeometrie telt, niet alleen eindpunten. Niet-verbonden groepen blijven
beschikbaar voor controle. Verbindingen via niet-geselecteerde objecten kunnen
ontbreken. Deze geometrische toets bewijst geen hydraulische verbinding.

De vaste categorievolgorde geldt over alle beheerders: **primair > verbonden
secundair > optioneel**. Primaire lijnen krijgen `-2 * burn_depth_m`, secundaire
lijnen `-burn_depth_m`: standaard -200 en -100 m. Dit zijn rekenkundige
verlagingen, geen bodemhoogtes. De keuze van doelen verandert deze regels niet.

## Duikers, sifons en hevels

Dit beschrijft de bestaande vectorvoorbereiding. Met `waternet = true` volgt
daarna de [gezamenlijke rasterbehandeling](#gezamenlijk-waternet), ook voor
BGT- en OSM-duikers. Die bepaalt de uiteindelijke inbranding en sluit
aanvullende duikercellen uit van het doelraster.

De productie leest `duikersifonhevel` voor de volledige tegelcontext, inclusief
buffers en beheerders die uitsluitend brandcontext leveren. In GKW is deze
laag verplicht; een lege laag is geldig. GKW-duikers met beheerdercode `80`
worden altijd uitgesloten. RWS-duikers worden uitsluitend uit de optionele
laag `duikersifonhevel` in `rws_hydamo.gpkg` gelezen. Een ontbrekende of lege
RWS-laag is geldig; een aanwezige laag moet leesbaar zijn en geldige identifiers
met code `80` hebben. De aanwezigheid wordt vastgelegd in `run.json`.

Beide uiteinden worden met maximaal **0,5 m** afstand aan een eenduidig primair
traject gekoppeld. De grenswaarde telt mee. Koppeling over bron- en
beheerdergrenzen is toegestaan; een duikergrens maakt geen nieuwe verbinding
met een nabije watergang. De technische
[koppelregels en beperkingen](../reference/afwateringseenheden.md#duikervoorbereiding)
staan bij de API.

```console
pixi run --environment afwateringseenheden afwateringseenheden --waterbeheercode 38 --duiker-tolerance 0.5 --max-aansluitlengte 50 --run-id duikers-50m
```

`--duiker-tolerance` stelt de koppelafstand per uiteinde in. De algemene
netwerktolerantie blijft 2 m. `--max-aansluitlengte` sluit directe aansluitstukken
tot en met de opgegeven lengte uit als afwateringsdoel. Zonder deze optie
(`None` in Python) behouden alle aansluitstukken hun doelstatus. Nul is geldig;
negatieve of niet-eindige waarden zijn ongeldig. De lengte wordt gemeten na
duikerknippen en fysieke objectgrenzen, vóór de maximumlengtesplitsing. De
selectie loopt niet verder door een keten van korte stukken.

Het gekoppelde duikertraject wordt altijd uitgesloten van primaire brandwerking
en doelen. Aansluitstukken blijven primair branden, ook wanneer ze geen doel
meer zijn. Optionele brandgeometrie en verbonden secundaire lijnen kunnen
nog steeds dezelfde rastercellen beïnvloeden. Er wordt geen ondergrondse
stromingsverbinding toegevoegd. Een andere aansluitlengte verandert het
gebrande DEM niet; de afwateringstoekenning kan wel veranderen.

### Controle in QGIS

Voor HYDAMO bestaat `bron_id` uit de bronnaam van de laag en het NEN3610-ID zonder
`NL.WBHCODE.`. Bijvoorbeeld: `hydroobject:38.Hydroobject.6984`.
`segment_key` voegt het deelnummer toe, bijvoorbeeld `:0003`.
`segment_id` is een gewoon geheel getal, gelijk aan de `fid` van het segment
in deze run. Afwateringseenheden en verbindingen gebruiken hetzelfde nummer.
Gesplitste multilijnen krijgen ook een deelnummer (`:deel0001`).
De IDs blijven gelijk als bronbestanden worden verplaatst of hernoemd.
De oorspronkelijke ID staat in `oorspronkelijk_bron_id` in `watersysteem.gpkg`;
bestand, laag en FID blijven afzonderlijk beschikbaar.
Dit geldt voor nieuwe runs. Bestaande uitvoer wordt niet aangepast.

Een voltooide run kan controleobjecten bevatten. Open `<run>/controle.gpkg`,
laag `duikersifonhevel`, samen met `watersysteem.gpkg`. Beoordeel `reden`,
`afstand_begin`, `afstand_eind`, de geometrie en de oorspronkelijke
bronidentificaties (`bronbestand`, `bronlaag`, `bron_fid` en `bron_id`). Er zijn
afzonderlijke meldingen voor geen match, één gekoppeld uiteinde, ambiguïteit,
een ontbrekend aaneengesloten traject en onbruikbare geometrie. Een duiker
zonder primaire match kan legitiem bij een secundaire watergang horen.

Mislukte koppelingen veranderen het netwerk niet gedeeltelijk. Andere duikers
worden wel verwerkt. Technische lees- en schrijffouten blijven fouten. Controleer
ook de uitgesloten trajecten in `intern/watersysteem.gpkg`, laag
`hydroobject_primair_delen`, en de kolommen
`brandgeschikt`, `doelgeschikt`, `duiker_ids` en `aansluit_duiker_ids` in
`hydroobject_segment`. De IDs in de duikerkolommen zijn JSON-lijsten.

De controlelaag wordt ook leeg geschreven en bij hervatten hersteld. Na
correctie en een nieuwe verwerking verdwijnen oude meldingen; andere lagen
in hetzelfde controlebestand blijven behouden. De controle is er ook als geen
afwateringseenheden kunnen worden geproduceerd.

## Optionele brandlagen

U kunt eigen GeoPackage-lagen met lijnen en polygonen gebruiken om het reken-DEM
te verhogen of te verlagen. Bereid de geometrie en attributen in QGIS voor.
Er worden geen bronnen voor deze lagen gedownload of watergangen automatisch
uit afgeleid. De lagen voegen geen afwateringsdoelen toe.

| QGIS-kolom | Waarde |
| --- | --- |
| `brandwaarde` | Relatieve wijziging in meters: negatief verlaagt, positief verhoogt. |
| `prioriteit` | Geheel getal; hoger heeft voorrang binnen de optionele lagen. |

De ingevulde objectwaarde gaat voor de laagdefault, die voor de globale default
gaat. Ontbrekende kolommen en `NULL` gebruiken de defaults. Zonder beschikbare
waarde volgt een fout. Het getal **0** is een expliciete waarde: geen
hoogtewijziging, maar bij hogere prioriteit wel blokkering van een lagere
optionele bewerking. Ongeldige ingevulde waarden worden niet door defaults vervangen.

De vaste rangorde is **primair > secundair > optioneel**, ongeacht de optionele
prioriteitsgetallen. Bij gelijke optionele prioriteit wint de grootste absolute
brandwaarde. Positief en negatief bij dezelfde prioriteit op dezelfde rastercel
is een fout, ook als een hogere prioriteit of vaste waterloop die cel overstemt.
Brandwaarden worden niet opgeteld. De gekozen wijziging wordt eenmaal toegepast.

Lijnen krijgen geen automatische breedtebuffer. Lever voor een fysieke breedte
een polygoon aan. Polygonen branden alle geraakte cellen in (`all_touched=True`);
lijnen gebruiken de bestaande lijnrasterisatie. Ook geometrieën die elkaar niet kruisen kunnen in één cel
terechtkomen. Branden verandert geen NoData buiten de geldige DEM-dekking.

### Gezamenlijk waternet

Zet `waternet = true` bovenaan de TOML. Met
`geisoleerde_branddiepte_m = 10.0` worden geïsoleerde HYDAMO-stelsels en
tertiaire waterlopen 10 m verlaagd. Aanvullende bronnen behouden hun
ingestelde `brandwaarde` buiten de beschermde HYDAMO-cellen.
Gebruik per laag `rol = "water"`, `rol = "duiker"` of `rol = "overig"` (standaard).
Een duikerlaag vereist ook `bron = "hydamo"`, `"bgt"` of `"osm"`.

| Situatie | Inbranding |
| --- | --- |
| Primaire waterloop buiten duikers | −200 m |
| Verbonden secundaire HYDAMO-waterloop | −100 m |
| HYDAMO-duiker secundair–primair of secundair–secundair, met route naar primair | −100 m |
| Geïsoleerd HYDAMO-stelsel, overige aanvoerduikers en tertiaire waterloop | −10 m |
| BGT-water en BGT/OSM-aanvoerduikers in het voorbeeld | −10 m |
| TOP10NL-waterdelen in het voorbeeld | −5 m |
| Uitsluitend primair–primair-duiker | Geen; ook aanvullende brandlagen worden onderdrukt |
| Duiker zonder twee vastgestelde aansluitingen | Geen afzonderlijke duikerinbranding; naar controle |

- De acht buren op het bestaande 2m-raster bepalen de waterverbindingen.
- Duikerlijnen worden via hun uiteinden gekoppeld. Een eindpunt van een
  secundaire/tertiaire waterloop op het duikertraject telt ook als aansluiting.
- BGT-vlakken blijven vlakken; afzonderlijke contactzones aan de rand gelden
  als aansluitingen. Een lijnkruising zonder aansluitende uiteinden volstaat niet.
- Registraties met wederzijds dekkende rastergeometrie binnen één buurcel
  worden als bronduplicaat behandeld: HYDAMO gaat voor BGT, BGT voor OSM.
  Meerdere mogelijke voorkeursregistraties gaan naar controle.
- Verbonden delen worden over overlappende tegelbuffers samengevoegd. Een
  verbinding buiten de beschikbare bronselectie kan niet worden vastgesteld.
- Alleen primaire en secundaire HYDAMO-waterlopen en daarvoor geschikte
  HYDAMO-duikers bepalen de bereikbaarheid voor 100 m inbranding.
  Een aanvullende waterlaag of ondiepe duiker maakt een geïsoleerde
  HYDAMO-waterloop dus niet alsnog diep.
- Aanvullende bronnen overschrijven geen primaire of secundaire HYDAMO-cellen
  en geen HYDAMO-duiker met 100 m verlaging.
- Alleen de geknipte primaire delen met `brandgeschikt = true` krijgen 200 m
  verlaging. De volledige primaire bronlijn wordt niet opnieuw ingebrand.
- Duiker en gekoppelde primaire duikerstukken worden afzonderlijk verrasterd.
  Hun rastercellen worden samengevoegd, zonder de lijnen geometrisch samen te voegen.
- Kruisende toegestane primaire en secundaire waterlopen behouden hun behandeling.
  Een cel kan maar één LDD-richting hebben; ongelijkvloerse routes blijven daardoor
  niet automatisch gescheiden.
- Bereikbaarheid van primaire **brandcontext** bepaalt diep/ondiep voor HYDAMO. RWS blijft
  primaire brandcontext; de bestaande beheerderselectie en LDD-toewijzing via
  RWS veranderen niet. Er is geen nieuwe RWS-stopregel.
- Duikers worden geen afwateringsdoelen. Het doelraster is bepalend; de
  vectorsegmenten behouden hun oorspronkelijke identifiers.

Deze rastertoets is een rekenaanname, geen bewijs van een fysieke aansluiting.
Ingebrande aanvoerduikers kunnen ook maaiveldwater langs hun traject aantrekken.
De ondiepe verlaging garandeert geen uitstroom uit iedere natuurlijke laagte.

De voorbereiding staat in `waternet/*.tif`: band 1 bevat de behandeling
(0 buiten het waternet, 1 primair, 2 diep HYDAMO, 3 ondiep, 4 uitgesloten),
band 2 de broncode, band 3 de duikercellen zonder afwateringsdoel en
band 4 de ondiepe verlaging in meters.
`controle.gpkg`, laag `duikers_waternet`, bevat alle duikerregistraties met
`behandeling`, `reden`, `diep_geschikt` en eventueel `voorkeur_id`.
`diep_geschikt` geeft aan of de duiker een HYDAMO-verbinding secundair–primair
of secundair–secundair heeft. Zonder verdere route naar primair blijft hij ondiep.
De oudere laag
`duikersifonhevel` beschrijft uitsluitend de voorafgaande primaire vectorkoppeling.

### TOML-configuratie

[Download het configuratievoorbeeld](../reference/voorbeelden/brandlagen.toml).
Het voorbeeld gebruikt bestaande BGT- en TOP10NL-GeoPackages. Plaats de TOML
naast `source_data` of pas de paden aan. Eigen correcties kunt u toevoegen.

De duikerlagen in het voorbeeld zijn vooraf geselecteerd voor de voorbeeldtegel
inclusief buffer. BGT bevat alleen `bgt_kunstwerkdeel` met `plus-type = duiker`;
OSM bevat lijnen met `tunnel=culvert`. Maak voor een ander gebied nieuwe selecties.
De TOML haalt deze gegevens niet zelf op.

| Laag | Brandwaarde | Voorrang |
| --- | ---: | --- |
| HYDAMO primair | −200 m | Vast, hoogste |
| HYDAMO secundair | −100 m verbonden, −10 m geïsoleerd | Waternet |
| HYDAMO tertiair | −10 m | Waternet |
| Eigen waterloopcorrecties (optioneel) | −10 m | Prioriteit 3 |
| `bgt_waterdeel` | −10 m | Prioriteit 2 |
| BGT-duikers (`bgt_duiker`) | −10 m bij een geldige aansluiting | Na HYDAMO |
| `top10nl_waterdeel_vlak` en `top10nl_waterdeel_lijn` | −5 m | Prioriteit 1 |
| OSM-duikers (`osm_culvert`) | −10 m bij een geldige aansluiting | Na HYDAMO en BGT |

De verlaging stuurt de LDD en stelt geen echte waterbodemhoogte voor.
Het voorbeeld gebruikt −10 m als standaard en −5 m voor beide TOP10NL-lagen.
De HYDAMO-behandeling gaat bij overlap voor deze aanvullende brandwaarden.
TOP10NL-lijnen worden zonder breedtebuffer ingebrand.
TOP10NL vult cellen aan waar BGT ontbreekt. Verlagingen worden niet opgeteld.
De TOML-volgorde bepaalt geen voorrang. Attributen op objecten blijven voorgaan
op de defaults. Alle objecten uit de gekozen lagen binnen het rekengebied doen
mee, zonder filter op status, type water of hoogteligging.

```toml
--8<-- "docs/reference/voorbeelden/brandlagen.toml"
```

`[defaults]` is optioneel en bevat globale defaults. Elke `[[lagen]]` heeft
verplicht `path` en `layer`, met optioneel `brandwaarde` en `prioriteit` als
laagdefaults. Relatieve paden worden ten opzichte van het TOML-bestand opgelost,
niet ten opzichte van de werkdirectory. Kolomnamen in QGIS staan vast;
onbekende configuratiesleutels worden afgewezen. Defaults zijn niet verplicht
als alle geselecteerde objecten zelf geldige waarden hebben.

```console
pixi run --locked afwateringseenheden --area alkmaar --brandlagen-config brandlagen.toml
```

De gewone productie controleert brandinvoer vóór de AHN-voorbereiding. Invoer-
en tekenconflicten worden gezamenlijk gemeld met bestand, laag en FID. De
conflictcontrole geldt op de gekozen rekenrasters, inclusief tegelbuffers,
onafhankelijk van de AHN-dekking. De controletijd hangt af van het aantal
geometrieën en hun overlap.

Een gevalideerde selectie wordt lokaal opgeslagen; workers lezen daaruit hun
eigen rekengebied. Bij ongewijzigde bronnen en instellingen wordt ook deze
voorbereiding hergebruikt. Bewerk bronbestanden niet tijdens een berekening.

### Afwateringseenheid aan een verbindingspunt koppelen

Gebruik beide bestanden uit dezelfde run. Koppel `segment_id` uit
`afwateringseenheden.gpkg` aan `van_segment` in de laag
`hydroobject_verbinding` van `watersysteem.gpkg`.

- De `fid` van de verbinding is het puntnummer.
- `naar_segment` is het nummer van het volgende segment.
- Een segment kan meerdere uitgaande verbindingen hebben, of geen.
- De richting volgt de bronlijnen; deze is niet uit de LDD afgeleid.

Deze nummers gelden binnen één run. Broninformatie en `segment_key` staan in
`hydroobject_segment`. De verbindingslaag bevat alleen de numerieke verwijzingen.

Gegevens van een gekoppelde stuw of gemaal staan in `objecttype`, `kunstwerk_bron_id`,
`kunstwerk_code`, `kunstwerk_naam` en `kunstwerk_waterbeheercode`. Zonder gekoppeld kunstwerk
zijn deze velden leeg. Het QGIS-formulier toont dan alleen de segmentkoppeling.
In oudere uitvoer heette het nummer `segment_fid` en bevatte `segment_id` tekst.

### Brandlagen controleren in QGIS

| Uitvoer binnen de runmap | Inhoud |
| --- | --- |
| `tiles/brandlagen.gpkg`, laag `brandlagen` | Optionele invoerobjecten, inclusief buffergebied. Met invoerwaarde, prioriteit, rol en bronherkomst. Het waternet kan de brandwaarde vervangen. |
| `tiles/<tegel>/brandbron.tif` | Winnende bron per cel, op hetzelfde rooster als het reken-DEM inclusief buffer. |

Broncode **1** is primair HYDAMO, **2** secundair HYDAMO. Vanaf **3** volgt
iedere opgegeven TOML-laag een eigen code, in configuratievolgorde. Deze codes
zijn labels, geen prioriteiten. De bronverwijzingen staan ook in de GeoTIFF-metadata
onder `broncodes`. **0** betekent geen inbranding; NoData ligt buiten de geldige
DEM-dekking. Een winnend gewoon brandobject met brandwaarde 0 houdt zijn eigen broncode.
Met het waternet volgen na de TOML-codes extra codes voor HYDAMO-duikers en
tertiaire waterlopen; de metadata bevat de bijbehorende legenda.

Open het bronraster en de brandobjecten in QGIS om overlap en aansluitingen te
controleren. Controleer daarna de LDD en afwateringsvlakken. Aanvullende
brandlagen maken geen nieuwe waterloopsegmenten of afwateringsdoelen.

Voor Python gebruikt u `Brandlaag`, `BrandlagenConfig`, `read_brandlagen_config`
en `read_brandlagen`; zie het
[uitvoerbare voorbeeld](../reference/bewerkte-lagen-produceren.md#afwateringseenheden).
Dat voorbeeld toont de losse bouwstenen; de normale productie-ingang voert
de volledige controle al vóór de zware bronvoorbereiding uit.

## Uitvoer en hervatten

Elke run staat onder `processed_data/afwateringseenheden/<gebied>/<run-id>/`.

| Bestand | Inhoud |
| --- | --- |
| `afwateringseenheden.gpkg` | Eén laag: `afvoergebiedaanvoergebied`. |
| `watersysteem.gpkg` | Vijf lagen: primaire, secundaire en niet-verbonden secundaire waterlopen, segmenten en verbindingen. |
| `controle.gpkg` | Niet-toegewezen gebieden, aanvullingen uit buurtegels, duikercontroles en bronobjecten zonder categorie. |
| `intern/watersysteem.gpkg` | Technische tussenlagen: volledige primaire bron en geknipte primaire delen. |
| `intern/watersysteem.gpkg.json` | Technische controle voor veilig hergebruik van het watersysteem. |
| `input/ahn.vrt` | Gebiedsspecifieke verwijzingen naar gedeelde AHN-tegels. |
| `tiles/tiles.gpkg` | Geselecteerde tegelkernen. |
| `tiles/brandlagen.gpkg` en `tiles/brandlagen.json` | Gevalideerde optionele brandobjecten en bron-/grididentiteit, indien gebruikt. |
| `tiles/<tegel-id>/` | Rasters, polygonen en status per rekentegel. |
| `productie.log` | Hoofdlog, inclusief de werkprocessen. |
| `run.json` | Instellingen, bronidentiteit, pakketversie en runstatus. |

Afwateringseenheden behouden de beheerder, oorspronkelijke identifiers en
bronbestand/laag/FID van hun doelsegment. `watersysteem.gpkg` bevat alle
primaire brandlijnen, verbonden secundaire lijnen en de controlelaag
`hydroobject_secundair_niet_verbonden`; alleen deelnemende primaire lijnen
staan in `hydroobject_segment`.
Bij duikervoorbereiding bevat `hydroobject_primair` uitsluitend de geschikte
brandgeometrie. In `intern/watersysteem.gpkg` bewaart `hydroobject_primair_bron` de volledige bron voor de
secundaire toets; `hydroobject_primair_delen` bewaart ook de uitgesloten
duikertrajecten van alle beheerders. De segmentlaag bevat ook ongeschikte
doelsegmenten; het doelraster gebruikt uitsluitend `doelgeschikt = true`.
In `controle.gpkg` bevat `hydroobject_zonder_categorie` uitgesloten
GKW-lijnen zonder categorie, met `uitsluitreden`.

Ook `niet_toegewezen` en `aanvulling_buurtegels` staan in `controle.gpkg`.
De tweede laag bewaart donor- en doeltegel en de keuzevolgorde. Bij uitsluitend
lege tegelresultaten blijven deze controles beschikbaar en meldt
de productie dat geen afwateringseenheden zijn gemaakt. Niet-toegewezen gebied
is niet automatisch correcte externe afwatering: brongaten, tegelranden en
rekenproblemen kunnen eveneens een oorzaak zijn. Toekenning aan het gekozen
waterschap wordt niet geforceerd.

Lever voor normaal gebruik de afwateringseenheden en het watersysteem.
Geef `controle.gpkg` apart mee voor beoordeling. De map `intern/` is bedoeld
voor technisch onderzoek. Bestaande runs worden niet automatisch verplaatst.

```console
pixi run --locked afwateringseenheden --area alkmaar --run-id proef
pixi run --locked afwateringseenheden --area alkmaar --run-id proef --resume
```

Fouten in afzonderlijke tegels verhinderen het samenvoegen, terwijl overige
onafhankelijke tegels worden afgewerkt. Hervatten hergebruikt geldige resultaten.
Zie [productiemappen](configuratie.md#productiemappen) voor de compatibiliteitsvoorwaarden.

De brandconfiguratie en bronidentiteiten worden vastgelegd in `run.json`.
Gewijzigde bronnen of instellingen vereisen bij de productie een nieuwe run-ID.
Dit geldt ook voor gewijzigde duikergeometrie, koppelafstand, aansluitlengte,
een gewijzigde eigen levering en een later toegevoegde RWS-duikerlaag. Zowel
bronbestanden als SQLite-WAL-wijzigingen worden gevolgd. Oude snapshots zonder
duikermetadata zijn bij duikervoorbereiding niet herbruikbaar.
Lagere Python-functies vernieuwen raster- en tegeluitvoer met gewijzigde
brandinvoer ook bij `overwrite=False`. Oude uitvoer zonder brandmetadata wordt
eenmalig opnieuw berekend; zie het
[API-hergebruikcontract](../reference/afwateringseenheden.md#dekking-en-hergebruik).

Gebruik voor eigen code de [Python-ingang](../reference/gebruik.md) of de
[lagere API](../reference/afwateringseenheden.md#dekking-en-hergebruik).
