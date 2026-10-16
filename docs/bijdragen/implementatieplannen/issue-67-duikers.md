---
editorial_status: ai
---

# #67 — Duikers en aansluitstukken

**Status:** bijgewerkt op 16 oktober 2026 op basis van de implementatie van #53
en de bevestigde grillingbesluiten. Dit document beschrijft gepland gedrag;
de implementatie en inhoudelijke acceptatie van #67 zijn nog niet uitgevoerd.

Issue: [#67 Duikers hebben geen eigen afwateringseenheid](https://github.com/d2hydro/waterlagen/issues/67).
Uitvoering: derde afzonderlijke branch en PR uit het
[gezamenlijke overzicht](index.md), na #65 en #53.

## Doel en scope

Alleen primaire hydroobjecten worden bij duikers, sifons en hevels opgeknipt,
op de aan de primaire lijnen gekoppelde uiteinden. Het tussenliggende
duikertraject krijgt geen primaire brandbewerking en geen eigen
uitstroompunt/afwateringsdoel. Bewaar het traject herkenbaar in de vectorgegevens
voor controle. Secundaire hydroobjecten worden door deze ingreep niet gewijzigd.

Pas dit toe op de volledige geselecteerde primaire context, inclusief overige
waterschappen en Rijkswateren, onafhankelijk van deelname als afwateringsdoel.
De bronselectie voor duikers staat hieronder vast. Doeluitsluiting geldt alleen
voor trajecten die volgens de doelmodus van #53 doelen kunnen leveren.

Direct aan een duiker grenzende stukken met lengte kleiner dan of gelijk aan
een instelbare grens kunnen worden uitgesloten als afwateringsdoel. Meet de
lengte na knippen op duikers en bestaande objectgrenzen, vóór de gewone opdeling
in maximale segmentlengtes. Loop niet recursief door een keten van korte stukken.
Deze aansluitstukken behouden hun primaire brandwerking.

De standaard is `None`: dan wordt geen extra aansluitstuk uitgesloten. Dit
schakelt niet de knipregel of uitsluiting van het duikertraject zelf uit.

De ingreep is geen absoluut brandverbod op rastercellen. Gewone optionele
brandlagen uit #65 mogen op het duikertraject blijven werken. Ook een daar
overlappende verbonden secundaire lijn behoudt haar brandwerking. Rijkswateren
behoren sinds #53 tot de primaire categorie en krijgen geen uitzondering op de
duikerregel. De vaste rangorde geldt voor de brandgeometrie die na selectie
overblijft: primair > verbonden secundair > optioneel.

## Relevante bestaande werking

- `sources.py:read_watersysteem_sources` levert volledige primaire en secundaire
  context, afzonderlijke primaire doelen en gemalen/stuwen van deelnemende
  beheerders. Duikerselectie mag dit doelafhankelijke kunstwerkfilter niet
  overnemen.
- `productie.py` bereidt alleen `sources.targets` met `sources.points` voor als
  netwerk, maar geeft `sources.primary` aan de schrijver voor branden en de
  gezamenlijke secundaire verbindingstoets.
- `workflow.py` knipt primaire hydroobjecten bij puntobjecten en deelt ze daarna
  op volgens een maximale segmentlengte.
- `lines.py:split_hydroobjecten_at_points` projecteert een punt op alle lijnen
  binnen de tolerantie. Deze helper kiest niet één bijbehorende watergang.
- Nabije eindpunten en puntobjecten spelen ook een rol in netwerkverbindingen.
  Een duikergrens als knippunt is niet automatisch een verbindend kunstwerkpunt.
- `raster.py` brandt de vaste lagen `hydroobject_primair` en
  `hydroobject_secundair`, onafhankelijk van `hydroobject_segment`.
- Het uitsluiten van een segment uit het doelraster stopt de vaste brandwerking
  dus niet. Beide geometrieselecties moeten expliciet worden verwerkt.
- Secundaire waterlopen krijgen nu geen eigen afwateringsdoelen; hun
  brandgeometrie blijft binnen deze scope ongewijzigd.
- `write_watersysteem` hergebruikt bestaande uitvoer na schema- en CRS-validatie.
  Deze controle bewijst nog niet dat duikerinvoer en instellingen overeenkomen.

Bij de lokale metadatacontrole op 16 oktober 2026 bevatte GKW de laag
`duikersifonhevel` met LineString-geometrie in EPSG:28992 en onder meer `code`,
`globalid`, `nen3610id` en `objectid`. Het schema bevat geen expliciet relatieveld
naar een hydroobject. De lokale RWS-GeoPackage bevat alleen `hydroobject`.
Deze controle betrof uitsluitend laagmetadata en schema; de objecten rond de
issuecoördinaat zijn nog niet inhoudelijk geverifieerd. Maak geen ongetoetste
aanname over een specifiek relatieattribuut of over toekomstige bronversies.

## Duikerbronnen en vervanging

Gebruik de laagnaam `duikersifonhevel` en de volgende bronregels:

| Bron | Laagcontract | Selectie en vervanging |
| --- | --- | --- |
| GKW HYDAMO | Verplicht aanwezig; leeg is geldig | Gebruik waterschapsduikers; sluit duikers met waterbeheercode `80` altijd uit. |
| Eigen waterschaps-GeoPackage via `eigen_hydamo` | Verplicht aanwezig; leeg is geldig | Vervangt alle GKW-duikers van de gekozen beheerder, ook voor brandcontext. Geen terugval op GKW. |
| RWS HYDAMO (`rws_hydamo.gpkg`) | Optioneel aanwezig; leeg is geldig | RWS-duikers komen uitsluitend uit deze bron, met beheerdercode `80`. Ontbreken betekent dat geen RWS-duikers zijn aangeleverd. |

Er zijn momenteel geen RWS-duikers aangeleverd. Als die beschikbaar komen,
worden ze aan de RWS-GeoPackage toegevoegd. Haal ze niet uit GKW en maak geen
vervangende kunstwerken. Een aanwezige maar onleesbare of ongeldige RWS-duikerlaag
is een fout; behandel die niet als een ontbrekende laag. Leg de aanwezigheid
van de optionele laag vast voor logging en hergebruik.

Breid het eigen-leveringscontract uit van `hydroobject`, `gemaal` en `stuw`
naar deze drie lagen plus `duikersifonhevel`. Bestaande eigen leveringen zonder
duikerlaag worden daarmee ongeldig; dit is een bevestigde wijziging van het
invoercontract. Controleer vóór AHN-voorbereiding de volledige eigen levering,
ook buiten de ruimtelijke selectie, op CRS en geldige `nen3610id`-waarden van
de gekozen beheerder. Een lege duikerlaag schakelt terugval op GKW niet in.

Lees duikers voor de volledige tegelcontext inclusief buffers, onafhankelijk
van `overige_waterschappen`. Behoud volledige geselecteerde geometrieën.
Hergebruik de bronlezers, GeoPandas-wrapper en CRS-helpers; gebruik niet de
puntobjectlezer voor duikerlijnen. Bewaar oorspronkelijke identificaties,
bronbestand, bronlaag en FID en maak samengestelde bronidentiteiten uniek
tussen bestanden. De geometrie van afzonderlijke onbruikbare duikers gaat
naar de controle-uitvoer volgens de onderstaande doorwerkregel.

## Koppelen en knippen

De instelbare koppeltolerantie is standaard **0,5 meter voor zowel begin- als
eindpunt van de duiker**. De afstandsvergelijking is inclusief de grenswaarde.
Deze instelling is afzonderlijk van de bestaande algemene netwerktolerantie.
Wijzig die algemene tolerantie niet als onderdeel van deze PR.

Gebruik de duikergeometrie en de primaire lijnen om een eenduidig bijbehorend
traject tussen de gekoppelde uiteinden te vinden. Een traject mag meerdere
oorspronkelijke primaire hydroobjecten omvatten. Beide uiteinden moeten correct
koppelen en het tussenliggende traject moet eenduidig zijn voordat een ingreep
wordt toegepast.

Een eenduidige koppeling mag over bron- en beheerdergrenzen lopen. Gebruik
beheerdergelijkheid niet als verplicht filter of als automatische doorslag
bij meerdere kandidaattrajecten. Bewaar de herkomst van zowel de duiker als
de betrokken primaire lijnen. Een toegelaten waterschapsduiker kan dus aan
een RWS-lijn koppelen; dit heft de uitsluiting van GKW-duikers met code `80`
niet op.

De 0,5 meter is een tolerantie voor de twee uiteinden, geen automatisch
ingestelde bufferbreedte voor het hele duikertraject. Gebruik evenmin een
algemene strookbuffer om alle nabije primaire watergangen te verwijderen.

Knip uitsluitend de gekoppelde primaire lijnen. Pas projectie niet blind toe
op iedere lijn binnen de tolerantie. Als meerdere bronobjecten op hetzelfde
bestaande knooppunt uitkomen, beoordeel de bijbehorende trajecten; meerdere
featurekandidaten betekenen niet noodzakelijk verschillende watergangen.
Kies bij verschillende mogelijke trajecten niet willekeurig op FID, rijvolgorde
of alleen de kortste netwerkroute.

Behandel duikergrenzen als splitsposities, niet als nieuwe verbindende
puntobjecten. Een duiker mag geen verbinding tussen nabije parallelle of
kruisende watergangen introduceren. Behoud de bestaande netwerkstructuur en
herkomst van bronobjecten; bepaal doelgeschiktheid en brandgeschiktheid apart.

Verwerk knipgrenzen en de bestaande fysieke objectgrenzen vóór de algemene
maximumlengtesplitsing. Classificeer directe aansluitstukken op dat niveau en
geef die classificatie door aan hun eventuele latere deelsegmenten. Een
verandering van de maximale segmentlengte mag de lengteclassificatie niet
inhoudelijk veranderen. Aan een vertakking geldt de lengteregel per direct
aansluitend stuk; breid de selectie niet recursief over verdere stukken uit.

## Niet goed gekoppelde duikers en controlebestand

Een mislukte of onduidelijke koppeling stopt de verwerking **niet**. Schrijf
de betreffende duiker met geometrie en reden naar `controle.gpkg`, laag
`duikersifonhevel`, in de uitvoermap van de berekening. Bij de gewone productie
staat dit bestand op `<run>/controle.gpkg`, ook als geen afwateringseenheden
worden geproduceerd. Bewaar minimaal bronbestand, bronlaag, oorspronkelijke
FID, beschikbare bron-ID en `reden`. Voeg waar
beschikbaar de afstanden van begin- en eindpunt toe voor controle in QGIS.

Onderscheid ten minste:

- geen primair hydroobject binnen de tolerantie;
- slechts één uiteinde gekoppeld of een uiteinde buiten de tolerantie;
- meerdere niet eenduidig te onderscheiden kandidaattrajecten;
- geen eenduidig aaneengesloten traject tussen de gekoppelde uiteinden;
- een afzonderlijk bronobject waarvan de geometrie geen bruikbare uiteinden
  oplevert.

Pas voor een niet goed gekoppelde duiker geen gedeeltelijke knip, uitsluiting
van brandwerking of uitsluiting van aansluitstukken toe. De betrokken primaire
geometrie behoudt de gewone verwerking, behalve waar een andere, wel correct
gekoppelde duiker een zelfstandige ingreep veroorzaakt.

Ga door met alle overige objecten en log één duidelijke waarschuwing met het
aantal controleobjecten en het pad naar `controle.gpkg`. Neem ook duikers zonder
primaire match op; ze kunnen legitiem bij secundaire watergangen horen, maar
blijven zo inspecteerbaar. Rapporteer objecten binnen de geselecteerde rekencontext,
niet alle niet-relevante duikers uit een landelijke bron.

Schrijf en valideer het controlebestand via de bestaande GeoPackage-helpers,
bij voorkeur met een tijdelijke kopie naast het doel en atomische vervanging.
Laat bij een nieuwe verwerking geen oude controlemeldingen staan voor inmiddels
correct gekoppelde objecten. Schrijf ook zonder meldingen een geldige lege
controlelaag; behoud eventueel aanwezige andere controlelagen. Bij hergebruik
moet het bijbehorende controlebestand beschikbaar en geldig zijn. Herstel
ontbrekende controle-uitvoer voordat een run als herbruikbaar wordt beschouwd.

Dit bestand staat naast de bestaande #53-controles `niet_toegewezen` en
`aanvulling_buurtegels` in het eindbestand, of bij uitsluitend lege tegelresultaten
in `tiles/controle.gpkg`. Verplaats of overschrijf die controles niet. Ook
`hydroobject_secundair_niet_verbonden` en `hydroobject_zonder_categorie` blijven
beschikbaar in het watersysteem.

Deze doorwerkregel betreft objecten die niet goed koppelen. Technische fouten
waardoor de bron niet kan worden gelezen of de uitvoer niet kan worden geschreven
blijven gewone fouten; ze mogen niet als een succesvolle berekening met nul
duikers worden gepresenteerd. Een aanwezige lege bronlaag is wel geldig.

## Brandgeometrie, netwerk en afwateringsdoelen

Bewaar de volledige primaire brongeometrie voor de bestaande classificatie
van verbonden secundaire waterlopen. `write_watersysteem` gebruikt die primaire
geometrie namelijk ook om secundaire verbindingen vast te stellen. Daar duiker-
trajecten verwijderen zou onbedoeld de secundaire brandwerking veranderen.

Maak drie expliciete selecties beschikbaar in de voorbereiding en het lokale
watersysteemsnapshot:

1. De volledige primaire brongeometrie van alle geselecteerde beheerders voor
   de gezamenlijke secundaire verbindingstoets, met de bestaande 2 m tolerantie.
2. De primaire brandgeometrie zonder correct gekoppelde duikertrajecten, met
   behoud van primaire brandwerking op aansluitstukken.
3. De volledige voorbereide segmentlaag van deelnemende doelbeheerders, met
   expliciete geschiktheid voor branden en afwateringsdoelen en duikerherkomst.

Bewaar uitgesloten duikertrajecten ook voor beheerders die alleen brandcontext
leveren herkenbaar in de vectoruitvoer. Breid het schrijf- en leescontract uit
zodat de volledige primaire bron niet alsnog ongefilterd wordt gerasteriseerd.
Pas dezelfde uitsluiting toe op RWS en omringende primaire lijnen; voeg geen
tweede brandroute toe die uitgesloten trajecten terugbrengt. Behoud lagere
Python-aanroepen zonder duikerinvoer. Geen nieuwe generieke beleidsengine is nodig.

Koppel duikers eenmaal tegen de volledige primaire context vóór de afhankelijke
brand- en doelvoorbereiding. Pas vervolgens de bestaande doelmodus toe op
segmenten en de bestaande selectie van gemalen/stuwen. Het omschakelen van
`overige_waterschappen` mag bij gelijke bronnen, grids en instellingen noch de
duikerkoppeling, noch de brandgeometrie, noch het gebrande DEM veranderen.
Een gewijzigde aansluitlengte verandert uitsluitend de doelgeschiktheid.

Rasteriseer voor het doelraster uitsluitend de geschikte segmenten. Behoud
hun opgeslagen GeoPackage-FIDs bij filtering: `raster.py` schrijft deze FIDs
en `pcraster.py` koppelt ze terug aan `segment_id`. Reset geen index en hernummer
geen FIDs om gaten na selectie op te vullen. Opnieuw splitsen kan uiteraard
nieuwe segmenten opleveren; bron-ID, segment-ID en FID blijven verschillende
identiteiten.

Uitsluiting betreft de betreffende geometrie, geen algemeen rastercelverbod.
Andere toegestane geometrie kan door rasterresolutie nog dezelfde cel raken.
Behoud de rasterisatiekeuzes uit #65 en test ook de grenscellen bij duikeruiteinden.

Bereken de oppervlakte-afwatering verder met het bestaande DEM/LDD-proces.
Voeg geen verborgen ondergrondse stromingsverbinding door de duiker toe en wijs
geen gebied willekeurig aan een buur toe. Het vervallen van brandwerking en
doelen kan stroomroutes of onverdeelde gebieden veranderen; maak dit onderdeel
van de inhoudelijke beoordeling.

## Python, productie en hergebruik

Voeg expliciete parameters toe voor duikerinvoer, koppeltolerantie
(standaard 0,5 m) en maximale lengte van uitgesloten aansluitstukken
(standaard `None`). Een opgegeven lengtegrens moet eindig en niet-negatief zijn.
Nul is geldig en sluit geen aansluitstuk met positieve lengte uit.

Behoud bestaande lagere Python-aanroepen zonder duikerinvoer. Zodra deze invoer
wel wordt aangeleverd, is de knipregel altijd van toepassing; de lengte-instelling
regelt uitsluitend de extra uitsluiting van aansluitstukken. De gewone productie
leest duikers volgens het bovenstaande bron- en vervangingscontract.
Maak tolerantie en aansluitlengte instelbaar via de normale productie-ingang
en CLI. Gebruik hiervoor gewone productspecifieke opties; breid de
brandlagen-TOML uit #65 niet uit met netwerkbewerkingen.

Verwerk de duikerbronnen, aanwezigheid van de optionele RWS-laag, uitsluiting
van GKW-code `80`, eigen vervanging, tolerantie, aansluitlengte en beleidsversie
in `run.json` en de controle op hergebruik. Hergebruik de bestaande controle
van bronidentiteiten, inclusief SQLite-WAL, en breid de laaglijsten uit.
Controleer drie niveaus:

1. Het voorbereide watersysteem en de segmentclassificatie.
2. DEM en afwateringsdoelraster.
3. Afgeleide tegelresultaten en hun samenvoeging.

Een geldig GeoPackage-schema of gelijk rastergrid is onvoldoende bewijs dat
de oude uitvoer bij de nieuwe duikerselectie hoort. Voeg aan de voorbereiding
en `write_watersysteem` controle op overeenkomstige invoer en instellingen toe;
oude snapshots zonder duikermetadata zijn bij duikerverwerking niet herbruikbaar.
Ook wijzigingen aan controleobjecten moeten bij herberekening worden verwerkt.

Behoud het productiecontract van #53: gewijzigde bronnen of instellingen
vereisen een nieuwe run-ID. Lagere Python-functies mogen gewijzigde invoer niet
stilzwijgend hergebruiken bij `overwrite=False`. Neem de duikeridentiteit mee
in de bestaande raster- en tegelcontrole en geef workers het voorbereide
snapshot. Het later toevoegen van een RWS-duikerlaag maakt afhankelijke oude
resultaten ongeschikt voor hergebruik. Hergebruik blijft mogelijk bij
ongewijzigde invoer; herdownload geen onaangetaste grote bronnen.

## Implementatiestappen

1. Voeg een gerichte lezer voor `duikersifonhevel` toe en breid
   `read_watersysteem_sources` uit volgens het bron- en vervangingscontract.
   Controleer invoer vóór AHN; behoud bron-FIDs, bron-ID's en correcte ruimtelijke
   selectie in bron-CRS. Sluit GKW-duikers met code `80` uit de selectie uit.
2. Voeg koppelen, geprojecteerde splitsposities en classificatie toe in de
   volledige primaire context in de watersysteemvoorbereiding. Scheid
   duikerknippen van de bestaande logica voor verbindende puntobjecten.
   Houd mislukte koppelingen apart als controleobjecten.
3. Breid het watersysteemsnapshot en `write_watersysteem` uit met volledige
   brongeometrie, gefilterde brandgeometrie, segmentherkomst en afzonderlijke
   geschiktheid voor primaire brandwerking en afwateringsdoelen.
4. Breid de primaire brandselectie en doelrasterisatie uit, zonder secundaire
   of optionele brandregels te veranderen. Bewaak de FID-koppeling.
5. Schrijf `<run>/controle.gpkg`, verbind parameters aan productie/CLI en geef de
   bestaande tegelverwerking de voorbereide gegevens door. Herhaal het
   volledige duikerkoppelproces niet per worker.
6. Werk de controle op hergebruik bij op watersysteem-, raster- en tegelniveau.
7. Voeg tests, publieke NumPy-docstrings, productie-instructies en een
   uitvoerbaar Python-voorbeeld met duikerinvoer en controle-uitvoer toe.

## Technische acceptatiecriteria

- De drie doelmodi van #53 blijven gelden: eigen waterschap, waterschappen
  gezamenlijk zonder RWS-doelen, en zonder waterschapscode alle beheerders
  inclusief RWS. Duikers van niet-deelnemende beheerders beïnvloeden wel de
  betreffende primaire brandgeometrie.
- GKW-duikers met code `80` worden altijd uitgesloten, ook bij een ontbrekende
  RWS-duikerlaag. Een ontbrekende of lege RWS-duikerlaag is geldig; een later
  toegevoegde laag wordt gebruikt en gevalideerd, inclusief code `80`.
- Een ontbrekende GKW- of eigen duikerlaag geeft vóór AHN een fout; een aanwezige
  lege laag is geldig. Eigen levering vervangt alle GKW-duikers van die beheerder,
  zonder fallback. Controleer ook afwijkende identifiers buiten de selectie.
- Eenduidige koppelingen over beheerder- en bronbestandsgrenzen zijn toegestaan,
  inclusief waterschapsduikers op RWS-lijnen. Beheerdergelijkheid lost ambiguïteit
  niet automatisch op. Herkomst en identiteiten blijven onderscheidbaar.
- Een eenduidige duiker binnen één primaire bronlijn wordt bij beide uiteinden
  geknipt; alleen het duikertraject verliest primaire brandwerking en doelstatus.
- Een eenduidig traject over meerdere primaire bronlijnen werkt eveneens.
- Beide eindpunten worden afzonderlijk getoetst op de instelbare 0,5 m;
  test ook exact op en net buiten de grens.
- Een nabije parallelle of kruisende lijn wordt niet onbedoeld geknipt of
  verbonden. Een omgekeerde tekenrichting verandert het resultaat niet.
- Geen match, een halve match en ambiguïteit leveren controleobjecten met
  reden op, stoppen de verwerking niet en veroorzaken geen gedeeltelijke ingreep.
- Een volgende run met gecorrigeerde koppelingen houdt geen verouderde
  controleobjecten over. De waarschuwing noemt aantal en uitvoerpad. Ook bij
  uitsluitend lege tegelresultaten bestaat de duikercontrolelaag; ontbrekende
  controle-uitvoer wordt bij hervatten hersteld. Bestaande #53-controles blijven
  behouden, ook in `tiles/controle.gpkg`.
- `None` behoudt alle aansluitdoelen; met een grens worden alleen directe
  stukken van lengte <= die grens uitgesloten. Test korter, gelijk en langer,
  een vertakking en een keten van korte stukken.
- Aansluitstukken blijven primair branden, ook als ze geen doelen meer zijn.
- Een gewone korte watergang zonder duiker verliest zijn doel niet.
- Secundaire classificatie en brandwerking blijven gelijk, inclusief een
  secundaire lijn die alleen nabij een uitgesloten duikertraject aansluit.
- Optionele brandlagen kunnen op duikertrajecten blijven werken. Primaire
  RWS-trajecten volgen dezelfde duikeruitsluiting als andere primaire lijnen;
  ongefilterde brandcontext brengt uitgesloten trajecten niet terug.
- Omschakelen van `overige_waterschappen` behoudt duikerkoppelingen en DEM bij
  gelijke bronnen en grids, terwijl de juiste doelen veranderen. Wijziging van
  de aansluitlengte behoudt de primaire brandgeometrie en het DEM.
- FID-naar-segment-ID-koppeling blijft juist wanneer tussen twee toegestane
  doelen een uitgesloten segment staat.
- Seriële/parallelle verwerking en duikers bij tegelranden leveren dezelfde
  classificatie op; controleobjecten worden niet per tegel gedupliceerd.
- Gewijzigde bron, tolerantie of lengtegrens maakt alle afhankelijke caches
  ongeldig; ongewijzigde invoer blijft herbruikbaar. Test ook een later toegevoegde
  RWS-duikerlaag, bronwijzigingen via WAL, oude watersysteemsnapshots zonder
  duikermetadata en gewijzigde invoer bij `overwrite=False` in de lagere API.

Gebruik kleine synthetische GeoPackages en rasters, zonder netwerkverkeer.
Werk gerichte tests bij voor watersysteem, rasters, subcatchments, tegels,
workers, productie en voorbeelden. Breid ook `test_afwateringseenheden_sources.py`
uit met de nieuwe combinaties. Voer de betrokken tests inclusief PCRaster uit met
`pixi run --environment afwateringseenheden pytest <test-bestanden>`.
Controleer gewijzigde Python met Ruff, voer voor het voorbeeld
`pixi run --environment afwateringseenheden pytest tests/test_python_examples.py` uit
en bouw met `pixi run --environment docs docs-build`.

## Afhankelijkheden en verificatie

Behoud in #65 afzonderlijke selectie voor vaste brandgeometrie, optionele
brandobjecten en afwateringsdoelen. De hoogteprioriteiten uit #65 worden niet
door de lengte-instelling van #67 vervangen.

#53 levert primaire Rijkswateren-context en, zonder gekozen waterschap, ook
RWS-doelen. Behoud deze doelmodi, volledige bronvervanging en de gezamenlijke
secundaire toets. De duikerbronregels staan in dit plan; de uitsluiting van
GKW-duikers met code `80` wijzigt niet de bestaande #53-selectie van gemalen
en stuwen. De volledige inhoudelijke Aa-en-Maas-vergelijking en menselijke
kaartbeoordeling staan volgens het #53-uitvoeringsverslag nog open. Neem deze
niet over als afgeronde validatie van #67.

Controleer de locatie `(179684.380, 406253.726)` uit het issue met de echte
brondata. Vergelijk zonder de ingreep, met standaard `None` en met een expliciete
lengtegrens waarmee de bedoelde korte aansluitingen worden geselecteerd.
Inspecteer de knipgrenzen, primaire brandgeometrie, het doelraster, stroomroutes,
afwateringseenheden en `controle.gpkg`. Leg bronversie en parameters vast.
De gebruiker beoordeelt deze resultaten inhoudelijk vóór acceptatie van de PR.

De afbeelding bewijst zonder bronattributen niet waar de exacte knipgrenzen
liggen. Gebruik haar niet als vervanging voor broncontrole. Als de echte
gegevens nog ontbreken, rapporteer de kaartcontrole als niet uitgevoerd;
synthetische tests kunnen wel al worden uitgevoerd.

Documentatie-impact: **confirmed**. De functionele uitleg over branden en
afwateringsdoelen verandert. De pagina
[Afwateringseenheden](../../bewerkte-lagen/afwateringseenheden.md) is beschermd
met `editorial_status: human`; rapporteer benodigde aanvullingen afzonderlijk.
Werk bij implementatie de bewerkbare productie-instructies, HYDAMO- en
RWS-bronbeschrijving waar relevant, API-referentie en voorbeelden bij.
Documenteer het gewijzigde contract voor eigen leveringen, de optionele
RWS-duikerlaag en het ontbreken van terugval op GKW voor RWS-duikers.
Documenteer nadrukkelijk dat een voltooide run nog controleobjecten kan
bevatten en hoe die in QGIS worden beoordeeld.

Dit plan blijft een intern werkdocument, uitgesloten via `exclude_docs` in
`mkdocs.yml`. Voeg het niet toe aan de gepubliceerde navigatie of overzichten.
