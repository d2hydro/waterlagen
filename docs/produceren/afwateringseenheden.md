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
`overig`; tertiaire en overige lijnen worden niet gebruikt. GKW-lijnen zonder
categorie blijven buiten branden en doelen en worden met een waarschuwing in
`hydroobject_zonder_categorie` bewaard, inclusief oorspronkelijke identificaties,
bronbestand, laag en FID. Er wordt geen categorie geraden. Onbekende ingevulde
waarden, ontbrekende categorieën in een eigen levering of RWS-bron,
tegenstrijdige kolommen en ontbrekende CRS-definities geven een fout.
Een bekend afwijkend CRS wordt expliciet naar het project-CRS getransformeerd.

### Gezamenlijke secundaire verbindingstoets

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

Een voltooide run kan controleobjecten bevatten. Open `<run>/controle.gpkg`,
laag `duikersifonhevel`, samen met `watersysteem.gpkg`. Beoordeel `reden`,
`afstand_begin`, `afstand_eind`, de geometrie en de oorspronkelijke
bronidentificaties (`bronbestand`, `bronlaag`, `bron_fid` en `bron_id`). Er zijn
afzonderlijke meldingen voor geen match, één gekoppeld uiteinde, ambiguïteit,
een ontbrekend aaneengesloten traject en onbruikbare geometrie. Een duiker
zonder primaire match kan legitiem bij een secundaire watergang horen.

Mislukte koppelingen veranderen het netwerk niet gedeeltelijk. Andere duikers
worden wel verwerkt. Technische lees- en schrijffouten blijven fouten. Controleer
ook de uitgesloten trajecten in `hydroobject_primair_delen` en de kolommen
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
een polygoon aan. Polygonen gebruiken celcentrumselectie; lijnen de bestaande
lijnrasterisatie. Ook geometrieën die elkaar niet kruisen kunnen in één cel
terechtkomen. Branden verandert geen NoData buiten de geldige DEM-dekking.

### TOML-configuratie

[Download het configuratievoorbeeld](../reference/voorbeelden/brandlagen.toml).
Het voorbeeld bevat geen GeoPackage; lever de twee genoemde lagen zelf aan.

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

Voor Python gebruikt u `Brandlaag`, `BrandlagenConfig`, `read_brandlagen_config`
en `read_brandlagen`; zie het
[uitvoerbare voorbeeld](../reference/bewerkte-lagen-produceren.md#afwateringseenheden).
Dat voorbeeld toont de losse bouwstenen; de normale productie-ingang voert
de volledige controle al vóór de zware bronvoorbereiding uit.

## Uitvoer en hervatten

Elke run staat onder `processed_data/afwateringseenheden/<gebied>/<run-id>/`.

| Bestand | Inhoud |
| --- | --- |
| `afwateringseenheden.gpkg` | Samengestelde afwateringseenheden. |
| `watersysteem.gpkg` | Voorbereid watersysteem voor alle geselecteerde tegels. |
| `controle.gpkg` | Laag `duikersifonhevel` met mislukte of onduidelijke koppelingen, ook geldig als deze leeg is. |
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
brandgeometrie. `hydroobject_primair_bron` bewaart de volledige bron voor de
secundaire toets; `hydroobject_primair_delen` bewaart ook de uitgesloten
duikertrajecten van alle beheerders. De segmentlaag bevat ook ongeschikte
doelsegmenten; het doelraster gebruikt uitsluitend `doelgeschikt = true`.
De aanvullende controlelaag `hydroobject_zonder_categorie` bevat uitgesloten
GKW-lijnen zonder categorie, met `uitsluitreden`.

Het eindbestand bevat ook `niet_toegewezen` en `aanvulling_buurtegels`.
De tweede laag bewaart donor- en doeltegel en de keuzevolgorde. Bij uitsluitend
lege tegelresultaten staan deze controles in `tiles/controle.gpkg` en meldt
de productie dat geen afwateringseenheden zijn gemaakt. Niet-toegewezen gebied
is niet automatisch correcte externe afwatering: brongaten, tegelranden en
rekenproblemen kunnen eveneens een oorzaak zijn. Toekenning aan het gekozen
waterschap wordt niet geforceerd.

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
