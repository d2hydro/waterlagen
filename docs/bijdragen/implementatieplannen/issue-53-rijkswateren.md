---
editorial_status: ai
---

# #53 — Afwateringseenheden met eigen watersysteem en omringende brandcontext

**Status:** op verzoek geïmplementeerd op 15 oktober 2026 op
`issue/53_opname_rijkswateren`. Technische controles en bevindingen staan onder
[Uitvoeringsverslag](#uitvoeringsverslag). De inhoudelijke acceptatie met echte
productiegegevens en menselijke kaartbeoordeling is nog niet voltooid.

Issue: [#53 Expliciet opnemen Rijkswateren](https://github.com/d2hydro/waterlagen/issues/53).
De scope is op verzoek verruimd. Hergebruik de aanwezige implementatie van
[#65 Configureerbare brandlagen](issue-65-brandlagen.md) op deze branch.
Houd de uitvoering in een afzonderlijke branch en PR voor #53.

## Doel en afbakening

Leid afwateringseenheden af voor heel Aa en Maas, waterbeheercode **38**. Gebruik
de eigen hydroobjecten en kunstwerken voor het watersysteem en gebruik de
hydroobjecten van overige waterschappen en Rijkswaterstaat als brandcontext.
Dezelfde werkwijze moet voor andere waterschappen werken, bijvoorbeeld code 27.

Maak deelname als afwateringsdoel afzonderlijk instelbaar voor overige
waterschappen. Zonder gekozen waterschap leveren ook Rijkswateren doelen.
Ondersteun daarnaast een eigen GeoPackage als volledige vervanging van de
GKW-objecten van het gekozen waterschap.

Deze scope vervangt het oude plan voor uitsluitend een optionele Rijkswaterenlaag
met een TOML-voorbeeld. Bronselectie, netwerkvoorbereiding, categoriegestuurd
branden, productie-invoer en controle-uitvoer moeten worden uitgebreid.

Buiten scope blijven:

- automatisch ophalen en bewerken van OSM tot Rijkswateren-hydroobjecten;
- porteren of uitvoeren van de voorbereidende Rijkswateren-productieketen;
- automatisch publiceren of uploaden naar de waterlagen-cloud;
- nieuwe kunstwerktypen of duikerverwerking uit #67;
- hydraulische berekening van kunstwerken;
- geometrische ontdubbeling op basis van alleen overlap tussen verschillende
  beheerders. De afgesproken vervanging per beheerder vindt wel plaats.

De ruimere interpretatie rondt niet automatisch alle oorspronkelijke onderdelen
van het issue af. Beschrijf de uitgevoerde scope later expliciet in de PR.

## Productiemodi en afwateringsdoelen

Gebruik één waterbeheercode voor de keuze van het waterschap en de selectie van
zijn bronobjecten. Voeg geen afzonderlijke `doelbeheerder` toe. Leid de beheerder
van objecten af uit `nen3610id`, volgens het bestaande patroon
`NL.WBHCODE.<code>.<rest>`.

| Productiemodus | Primaire lijnen met afwateringsdoelen | Lijnen die uitsluitend brandcontext zijn |
| --- | --- | --- |
| Waterschap gekozen, overige waterschappen uit | Eigen waterschap | Overige waterschappen en Rijkswaterstaat |
| Waterschap gekozen, overige waterschappen aan | Eigen en overige waterschappen | Rijkswaterstaat |
| Geen waterschap gekozen | Alle geselecteerde waterschappen en Rijkswaterstaat | Geen afzonderlijke beheerdergroep |

De vlag voor overige waterschappen staat standaard **uit**. Zij bepaalt alleen
deelname als afwateringsdoel; de omringende hydroobjecten blijven in beide
standen beschikbaar voor het branden. Secundaire lijnen leveren nooit zelf
afwateringsdoelen.

Zonder waterbeheercode geldt de laatste rij ook voor een geografische uitsnede,
zoals `--area alkmaar`. Rijkswaterdoelen hangen dus niet af van de omvang of naam
van het gebied. Een eigen GeoPackage en de vlag voor overige waterschappen zijn
alleen toegestaan wanneer een waterbeheercode is opgegeven.

Dit verandert de huidige productie: die gebruikt alle ruimtelijk geselecteerde
GKW-beheerders als watersysteem, ook bij selectie van één waterschap. Leg dit
gedragsverschil vast in productie-instructies en tests.

## Bronnen en vervanging

### GKW-HyDAMO

Behoud de bestaande downloader en de bestaande GKW-bron voor waterschapsobjecten.
Gebruik de gedeelde bronvoorbereiding voor lokaal hergebruik, offline werken en
expliciete bronvernieuwing. GKW blijft nodig wanneer een eigen GeoPackage wordt
opgegeven: die vervangt alleen de gekozen beheerder, niet de omringende bronnen.

### Rijkswateren

De handmatig gepubliceerde bron staat op
[de waterlagen-cloud](https://waterlagen.d2hydro.nl), in map `hydamo`, bestand
`rws_hydamo.gpkg`, laag `hydroobject`.

Op 15 oktober 2026 is de redirect en het bestand gecontroleerd. De openbare URL
verwees naar een Nextcloud-share. Het bestand is uitsluitend in het geheugen
uitgelezen: 2.305 LineStrings in `EPSG:28992`, met `categorieoppervlaktewater`
gelijk aan `primair`. De attributen omvatten `globalid`, `nen3610id`,
`categorieoppervlaktewater`, `naam`, `bron`, `osm_id` en `osm_laag`.
Dit is een waarneming van die bronversie, geen vast feature-aantal voor tests en
geen verklaring van volledige of inhoudelijk gevalideerde landelijke dekking.

Volg eerst de redirect naar de openbare share en bepaal daarna de download van
het afzonderlijke bestand. Een sharepagina is geen GeoPackage. Maak de bronlocatie
instelbaar en leg de actuele sharetoken niet als vaste pakketconfiguratie vast.
Gebruik generieke download-, timeout-, voortgangs- en payloadvalidatiehelpers.
Valideer nieuwe bestanden vóór atomaire vervanging van een bestaande bron.
Een geldige lokale bron moet zonder netwerkverkeer herbruikbaar zijn.

Sla de bron via `DataStore` lokaal op. Publicatie blijft een handmatige stap van
de gebruiker; de productie haalt de gepubliceerde bron op of hergebruikt haar.

Gebruik **uitsluitend deze bron voor Rijkswaterstaat-hydroobjecten**. Sluit
GKW-hydroobjecten met code `80` volledig uit, voor branden én doelen. Eventuele
GKW-gemalen en -stuwen van code `80` blijven beschikbaar wanneer Rijkswaterstaat
doelen levert. De RWS-distributie hoeft zelf alleen `hydroobject` te bevatten.
Vul ontbrekende Rijkswaterlijnen niet automatisch vanuit GKW aan.

De voorbereidende code in
[`d2hydro/rws_hydroobject`](https://github.com/d2hydro/rws_hydroobject)
blijft achtergrondinformatie. Het produceren van die bron hoort niet bij deze
implementatie. De bron-URLs worden bij latere publicatie canoniek gedocumenteerd
op een bronpagina; dit plan blijft een intern werkdocument.

### Eigen GeoPackage van een waterschap

Een opgegeven eigen GeoPackage vervangt **alle** GKW-hydroobjecten, gemalen en
stuwen van de gekozen waterbeheercode. Verwijder deze GKW-objecten ook uit de
brandcontext en bij ingeschakelde deelname van overige waterschappen.
Gebruik geen fallback naar GKW om gaten in de eigen levering te vullen.

Vereis de lagen `hydroobject`, `gemaal` en `stuw`. Kunstwerklagen mogen leeg zijn;
een ontbrekende laag geeft een duidelijke fout. Controleer de identificaties
in de gebruikte lagen: ontbrekende, ongeldige of van de gekozen beheerder
afwijkende `nen3610id`-waarden worden afgewezen, niet stilzwijgend weggefilterd.
Een levering met meerdere beheerders moet vooraf worden geselecteerd.

Controleer dit broncontract vóór zware rastervoorbereiding. De eis voor drie
lagen geldt voor de eigen vervangende levering, niet voor `rws_hydamo`.

### Normalisatie en herkomst

De bestaande GKW-reader gebruikt `categorieoppwaterlichaam`; de gecontroleerde
RWS-bron gebruikt `categorieoppervlaktewater`. De bestaande alias voor
filterargumenten normaliseert bronkolommen niet automatisch. Voeg een expliciete,
kleine normalisatiestap toe en valideer de benodigde categorieën. Ken onbekende
waarden niet stilzwijgend aan primair, secundair of een andere beheerder toe.

Na controle van de aangeleverde GKW-bron heeft de gebruiker bevestigd dat
`overig`, net als `tertiair`, buiten branden en doelen blijft. GKW-lijnen met
een ontbrekende categorie worden met een waarschuwing uitgesloten en in
`hydroobject_zonder_categorie` bewaard, inclusief identifiers, bronbestand,
laag, FID en uitsluitreden. Onbekende ingevulde categorieën blijven een fout.
Deze uitzondering geldt niet voor een eigen levering of de RWS-bron.

Gebruik de bestaande CRS-helpers en de GeoPackage-reader voor gemeten geometrieën.
Een ontbrekend CRS is een fout; transformeer bekende bron-CRS expliciet naar
`settings.crs`. Bewaar oorspronkelijke identifiers, bronbestand, laag en FID.
Zorg dat samengestelde bron- en segmentidentiteiten niet botsen tussen bestanden;
gebruik geen GeoPackage-FID als globale bronidentiteit.

## Ruimtelijke selectie en netwerkvoorbereiding

Selecteer de volledige rekentegels die het gekozen gebied raken en hun buffers,
volgens de bestaande gridinstellingen. Gebruik alle andere waterschappen met
objecten binnen die context, zonder afzonderlijke lijst administratieve buren.
Behoud de volledige geometrie van geselecteerde objecten; knip bronlijnen niet
op de waterschapsgrens af.

Bereid uitsluitend de primaire lijnen van deelnemende beheerders voor als
afwateringsdoelen. Gebruik daarvoor dezelfde bestaande functies voor splitsen
bij gemalen en stuwen, maximale segmentlengte en verbindingen. Gebruik alleen
kunstwerken van deelnemende beheerders. Bij landelijke combinatie kunnen deze
kunstwerken volgens de bestaande nabijheidsregels ook lijnen van een andere
deelnemende beheerder splitsen.

Primaire Rijkswaterlijnen doorlopen deze voorbereiding alleen zonder gekozen
waterschap. Er komt geen afzonderlijke Rijkswateren-segmentatie. Het ontbreken
van Rijkswaterstaat-kunstwerken mag niet tot verzonnen kunstwerken leiden.

### Verbonden secundaire lijnen

Classificeer **alle geselecteerde secundaire lijnen gezamenlijk**, tegen **alle
geselecteerde primaire lijnen**, inclusief lijnen van beheerders zonder doelen.
Doe dit voor het hele geselecteerde netwerk, niet opnieuw per tegel of alleen
tegen de doelgeometrieën.

Hergebruik `split_connected_secondary_hydroobjecten` en de bestaande toets:

- secundaire lijnen op maximaal de verbindingstolerantie vormen groepen;
- een groep is verbonden zodra minstens één lid binnen die tolerantie van een
  primaire lijn ligt, eventueel via andere secundaire lijnen;
- de standaardtolerantie blijft 2 m;
- de minimumafstand tussen volledige lijngeometrieën telt, niet alleen eindpunten;
- richting, hoogte en kunstwerkhydrauliek worden niet gebruikt.

Brand uitsluitend de verbonden secundaire groepen. Bewaar de uitgesloten lijnen
voor controle. Dit criterium geldt voor eigen en externe lijnen, met en zonder
gekozen waterschap. Een aansluiting uitsluitend op de Maas kan dus voldoende
zijn, ook wanneer de Maas alleen brandcontext is.

De classificatie blijft beperkt tot de beschikbare geselecteerde bronnen. Een
keten via niet-geselecteerde objecten kan ontbreken. Verbindingen buiten de
selectiegrens kunnen wel meetellen wanneer de volledige betrokken geometrieën
zijn ingelezen. Presenteer deze geometrische toets niet als bewezen hydraulische
verbinding.

## Brandwerking en hergebruik van #65

De vaste rangorde wordt **alle primaire lijnen > alle verbonden secundaire
lijnen > gewone optionele brandlagen**, ongeacht beheerder of deelname als doel.
Een externe primaire lijn wint dus van een eigen secundaire lijn.

Gebruik één ingestelde `burn_depth_m`: primair krijgt `-2 * burn_depth_m`,
secundair `-burn_depth_m`. Bij de huidige standaard zijn dat -200 en -100 m.
Dit zijn rekenkundige verlagingen, geen werkelijke bodemhoogtes. Tel waarden
bij overlap niet op en voer geen handmatige formule-evaluatie in TOML in.

De technische voorkeursroute is een expliciete primaire/secundaire categorie in
de voorbereide brandinvoer. Hergebruik de voorzieningen uit #65 voor validatie,
herkomst, snapshots, rasterisatie, workers en cachecontrole. Gewone optionele
lagen behouden hun bestaande QGIS/TOML-contract, defaults, prioriteiten,
tekenconflicten en nulwaarden. Gebruik een hoog optioneel `prioriteit`-getal niet
als vervanging van de categorievolgorde.

Houd doelgeometrieën en brandgeometrieën expliciet gescheiden. De bestaande
`write_watersysteem` classificeert secundaire lijnen tijdens het schrijven tegen
de meegegeven primaire lijnen. Voorkom dat daar de gezamenlijke classificatie
alsnog wordt vervangen door een toets tegen alleen de doelbeheerders.

Laat de rasterberekening dezelfde categorieën combineren; voeg geen tweede
brandroutine of Rijkswateren-specifieke rastervertakking toe. Het omschakelen
van de doelvlag moet bij dezelfde bronnen, grids en brandinstellingen dezelfde
brandselectie en hetzelfde gebrande DEM opleveren. Het segmentraster en de
afwateringseenheden mogen daarbij wel veranderen.

Behoud CRS, grid, resolutie, NoData, schaal, offset, compressie en overviews.
Branden maakt geen geldige hoogtes buiten de DEM-dekking.

## Productie-invoer, caches en uitvoer

Voeg een expliciete vlag voor deelname van overige waterschappen en een optioneel
pad voor de eigen GeoPackage toe aan de productie-API en CLI. De definitieve
parameternamen worden bij implementatie gekozen; hun hierboven vastgelegde
betekenis staat vast. Behoud de bestaande generieke `brandlagen`-invoer en
`--brandlagen-config` voor aanvullende gebruikerslagen.

Voer bronvervanging en validatie uit vóór de voorbereiding van AHN. Leg in
`run.json` en toepasselijke cache-identiteiten ten minste vast:

- gekozen waterbeheercode en deelname van overige waterschappen;
- GKW-, RWS- en eventuele eigen bronidentiteiten en relevante lagen;
- beleid voor bronvervanging en categorie-normalisatie;
- de gezamenlijke secundaire verbindingstoets en tolerantie;
- brandcategorieën, `burn_depth_m` en instellingen van gewone optionele lagen;
- doelselectie, grid en bronherkomst van voorbereide resultaten.

Een gewijzigde doelvlag maakt oude segmenten en afwateringseenheden ongeschikt
voor hergebruik, ook als het DEM gelijk blijft. Wijzigingen in bronnen,
verbindingsbeleid of brandinstellingen moeten de daarvan afhankelijke caches
vernieuwen. Bewaar het #65-contract voor controle vóór workers, offline bronnen,
expliciet vernieuwen en het niet hergebruiken van mislukte berekeningen.

Knip de uiteindelijke afwateringseenheden niet op de administratieve gebiedsgrens
af. Bij ingeschakelde overige waterschappen blijven ook hun eenheden herkenbaar
in de uitvoer. Bewaar beheerder en bronherkomst om resultaten te kunnen duiden.

Maak niet-verbonden secundaire lijnen en niet-toegewezen gebieden zichtbaar in
controle-uitvoer. Forceer geen volledige toekenning aan het gekozen waterschap.
Noem niet-toegewezen gebied niet automatisch correcte externe afwatering: ook
brongaten, tegelranden of rekenproblemen kunnen een rol spelen. Houd het bestaande
aanvullen uit buurtegels herkenbaar en controleer dit bij de inhoudelijke review.

## Implementatiestappen

1. Controleer de aanwezige #65-bouwstenen en rechtstreeks betrokken tests.
2. Voeg RWS-download en lokale opslag toe met de gedeelde download- en bronpolicy;
   ondersteun de openbare redirect en handmatige publicatie.
3. Implementeer eigen-bronvalidatie, categorie-normalisatie en volledige
   beheerdervervanging, inclusief uitsluiting van GKW-hydroobjecten met code 80.
4. Maak expliciete selecties voor primaire doelen, deelnemende kunstwerken en
   het volledige netwerk voor brandcontext. Classificeer secundair gezamenlijk.
5. Breid de voorbereiding uit met brandcategorieën en hergebruik #65; houd
   gewone optionele lagen compatibel en scheid netwerkdoelen van brandwerking.
6. Verbind dit met productie-API, CLI, manifests, cachecontrole en controle-uitvoer.
7. Voeg gerichte tests, broninformatie, productie-instructies en uitvoerbare
   voorbeelden toe. Rapporteer bevindingen voor beschermde documentatie apart.
8. Voer de inhoudelijke vergelijking voor Aa en Maas uit en laat deze door de
   gebruiker beoordelen vóór inhoudelijke acceptatie.

## Technische acceptatie

Gebruik kleine synthetische GeoPackages en rasters en gemockte downloads.
Hergebruik de tests uit #65; dupliceer geen volledige generieke brandsuite.
Controleer ten minste:

- de drie productiemodi uit de tabel, inclusief een geografische uitsnede zonder
  waterbeheercode en afwijzing van beheerderopties zonder gekozen beheerder;
- eigen vervanging voor bijvoorbeeld code 30 en 38: geen GKW-object van die
  beheerder blijft in doelen, kunstwerken of brandcontext achter;
- ontbrekende lagen, lege kunstwerklagen en ontbrekende/afwijkende identifiers
  in een eigen levering, vóór zware rasterverwerking;
- RWS-categorie-normalisatie, CRS, bronherkomst en uitsluiting van GKW-code 80
  hydroobjecten, met behoud van toepasselijke GKW-kunstwerken;
- RWS als uitsluitend brandcontext bij waterschapsproductie en als primaire
  segmentdoelen zonder gekozen waterschap;
- verbonden secundaire ketens over beheerdergrenzen en via RWS, en uitsluiting
  van werkelijk losse groepen bij alle productiemodi;
- externe primaire lijn over eigen secundair en eigen primaire lijn over extern
  secundair, met gekoppelde branddieptes en zonder optelling;
- gelijke brandselectie en DEM bij omschakelen van de doelvlag, maar de juiste
  gewijzigde doelraster- en eenhedenselectie;
- behoud van gewone optionele brandregels en van rastereigenschappen/NoData;
- hergebruik en invalidatie van bron-, netwerk-, brand-, DEM- en tegelresultaten;
- cloudredirect, foutpagina in plaats van GeoPackage, HTTP-fouten, onvolledige
  download, lokale reuse zonder netwerk en behoud van een bestaand bestand bij
  een mislukte vernieuwing;
- zichtbare uitgesloten secundaire lijnen en niet-toegewezen gebieden.

Voer de gerichte afwateringseenheden-, download-, productie-, CLI- en
voorbeeldtests uit met pixi. Controleer gewijzigde Python met Ruff. Bouw
documentatie met `pixi run --environment docs docs-build`. Unit tests doen geen
echte downloads en vormen geen inhoudelijke landelijke validatie.

## Inhoudelijke acceptatie

Gebruik Aa en Maas, waterbeheercode 38, met de Maas, Brabantse kanalen en relevante
grensgebieden. Leg bronversies, publicatielocatie, eigen levering indien gebruikt,
doelmodus en rekeninstellingen vast. Vergelijk bij gelijke bronnen en grids:

- de doelvlag uit en aan: gelijk DEM, juiste verschillen in doeltoekenning;
- een run met en zonder RWS-brandcontext als gecontroleerde vergelijking van
  het effect op stroming, niet als extra standaardproductiemodus;
- verbonden en uitgesloten secundaire groepen, met name bij beheerdergrenzen;
- niet-toegewezen gebieden, randproblemen, aanvulling uit buurtegels en
  onverwachte grensverschuivingen;
- eigen bronvervanging, indien een eigen levering beschikbaar is.

Controleer aanvullend in een geschikte uitsnede zonder waterbeheercode dat
Rijkswatersegmenten eigen afwateringseenheden krijgen. Dit vereist geen volledige
landelijke productie voor de technische acceptatie en bewijst geen landelijke
bronkwaliteit.

De gebruiker beoordeelt de kaarten inhoudelijk. Een verdiept DEM bewijst geen
betere hydrologische afbakening. Markeer deze controle niet als voltooid zolang
de productiegegevens, berekeningen of menselijke beoordeling ontbreken.

## Documentatie en aansluiting op andere plannen

Documentatie-impact: **confirmed**. Voeg bij implementatie een bronpagina voor
Rijkswateren toe met actuele, geverifieerde verwijzingen en bronbeperkingen.
Werk productie-instructies bij voor bronvervanging, de doelvlag, de gewijzigde
standaard bij waterschapsselectie en Rijkswaterdoelen zonder waterbeheercode.
Documenteer Python-interfaces in docstrings en API-reference; plaats uitvoerbare
voorbeelden op de bestaande canonieke locatie.

De beschermde pagina [Afwateringseenheden](../../bewerkte-lagen/afwateringseenheden.md)
beschrijft nu een productie zonder aanvullend beheerderfilter. Zij moet bij
implementatie ook de categorievolgorde over alle beheerders, gezamenlijke
secundaire classificatie, doelmodi en controle-uitvoer verklaren. De beschermde
[bronlagenindex](../../bronlagen/index.md) mist dan de nieuwe Rijkswaterenbron.
Rapporteer deze bevindingen afzonderlijk; dit plan verleent geen toestemming om
de beschermde pagina's te wijzigen.

[#67](issue-67-duikers.md) blijft een afzonderlijke implementatie. De bestaande
tekst daarin gaat nog uit van Rijkswateren als gewone optionele brandlaag zonder
doelen. Die aanname moet vóór uitvoering van #67 met dit vernieuwde #53-plan
worden verzoend. De nieuwe primaire RWS-brandcategorie mag niet zonder nadere
beoordeling als de oude optionele klasse worden behandeld. Implementeer in #53
geen duikeruitsluitingen en herstel later geen uitgesloten primaire trajecten
door ze nogmaals vanuit ongefilterde brandcontext toe te voegen. Bewaar de
volledige primaire bron voor de secundaire verbindingstoets en houd branden en
doeltoekenning afzonderlijk.

[#63](issue-63-bounds.md) blijft verantwoordelijk voor vrije gebiedsselectie.
Voeg daarvoor in #53 geen tweede gebiedsinterface toe. Deze plannen blijven
uitgesloten van de MkDocs-site; pas voor dit plan geen navigatie of publicatie
aan.

## Uitvoeringsverslag

De productie gebruikt `overige_waterschappen` / `--overige-waterschappen` en
`eigen_hydamo` / `--eigen-hydamo`. De bestaande gebiedscode bepaalt tevens de
doelbeheerders. `rijkswateren_url` / `--rijkswateren-url` configureert de bron.
De gedeelde bronpolicy regelt lokaal hergebruik, offline werken en vernieuwen.

`read_watersysteem_sources` levert volledige primaire/secundaire brandcontext
en afzonderlijke primaire doelen en deelnemende kunstwerken. De bestaande
categorielagen in `watersysteem.gpkg` blijven het gevalideerde lokale snapshot
voor rasterisatie en workers; `brandcategorie` maakt de herkomst expliciet.
`write_watersysteem` krijgt de volledige primaire context en classificeert
secundair daarom gezamenlijk, onafhankelijk van de voorbereide doelsegmenten.
De bestaande #65-rasterroutine en optionele brandconfiguratie blijven in gebruik.

Afwateringseenheden behouden beheerder en bronherkomst. De controlelagen
`niet_toegewezen` en `aanvulling_buurtegels` worden meegeleverd; bij uitsluitend
lege resultaten staan ze in `tiles/controle.gpkg`. De uitgesloten secundaire
lijnen staan in het watersysteem. Bronidentiteiten, inclusief SQLite-WAL,
worden gecontroleerd vóór hergebruik. Een gewijzigde doelmodus vereist een
nieuwe run; ontbrekende of mislukte resultaten worden opnieuw berekend.

De echte RWS-download via de openbare redirect is uitgevoerd en gecontroleerd:
2.305 lijnen in EPSG:28992, met de verwachte categorie en identifiers. Dit is
een technische broncontrole, geen inhoudelijke acceptatie. De bestanden blijven
in de genegeerde gegevensmap. De bronpagina bevat de geverifieerde verwijzingen.

### Technische controles

De gerichte acceptatiesuite heeft 266 geslaagde tests in de omgeving
`afwateringseenheden`, inclusief echte PCRaster-berekeningen voor de drie
doelmodi, de gedeelde downloads, productie/CLI en offline voorbeelden.
Rasterio/Affine geeft bestaande deprecatiewaarschuwingen. Ruff en de strikte
documentatiebuild zijn gecontroleerd. De beschermde pagina's zijn niet gewijzigd.
Na de bevestigde GKW-categoriepolicy zijn nogmaals 91 gerichte tests geslaagd,
inclusief echte PCRaster-berekeningen, controle-uitvoer en vervanging van oudere
snapshots zonder de nieuwe controlelaag. Ruff en de strikte documentatiebuild
slagen ook na deze aanvulling.

### Inhoudelijke vergelijking

De gebruiker heeft een bestaande DataStore aangeleverd, lokaal ingesteld via
de genegeerde `.datastore`. De waterschapsgrenzen identificeren Aa en Maas als
code **38**, niet 30. De gebruiker heeft gebruik van code 38 bevestigd; het
plan en de productievoorbeelden zijn daarop gecorrigeerd.

De selectie bestaat uit 30 volledige rekentegels. De context vraagt 150 AHN-
brontegels, waarvan er bij inventarisatie 121 beschikbaar waren. GKW bevat
ook `overig` en enkele lijnen zonder categorie. De gebruiker heeft de policy
voor uitsluiting met waarschuwing en controle-uitvoer bevestigd. In de exacte
rekencontext zijn twee GKW-lijnen zonder categorie aangetroffen. Alle 29
ontbrekende AHN-tegels zijn opgehaald en gevalideerd; bestaande tegels zijn
hergebruikt.

Het echte netwerk bevat 28.574 primaire brandlijnen, waaronder 167 RWS-lijnen,
en 11.539 doelsegmenten van uitsluitend Aa en Maas. Van 26.606 secundaire lijnen
zijn er 25.559 verbonden en 1.047 uitgesloten. In het gecontroleerde netwerk
zonder RWS blijven de doelsegmenten en de geselecteerde secundaire lijnen exact
gelijk. Bij de kunstwerkvoorbereiding vallen 64 punten buiten de bestaande
koppeltolerantie van 2 m.

De echte Maasuitsnede zonder waterschapscode (RD 150000–160000,
410000–420000) is afgerond. Zij bevat 1.256 eenheden, waarvan 49 van RWS,
1.011 van Aa en Maas, 165 van beheerder 9 en 31 van beheerder 27.
De toegewezen oppervlakte is 97,996916 km²; 2,003084 km² blijft niet toegewezen.
Er is bij deze enkele tegel geen aanvulling uit buurtegels. De controlekaart
en tellingen staan lokaal onder `processed_data/afwateringseenheden_review/`
als `issue53_rws_doelen.png` en `issue53_uitsnede_controle.json`.
Dit bevestigt technisch de doelmodus, niet de hydrologische juistheid.

De volledige Aa-en-Maas-vergelijking, het gecontroleerde rasterexperiment zonder
RWS-brandcontext en de kaartbeoordeling zijn nog open. De berekeningen lopen
met dezelfde grids, 2 m resolutie, 2 km buffers en vaste seed. Er is geen eigen
levering verstrekt. Synthetische controles vervangen de inhoudelijke vergelijking
niet.

### Afzonderlijke documentatiebevindingen

Documentatie-impact: **confirmed**. Bronpagina, productie-instructies, gedeelde
CLI-uitleg, API-reference en uitvoerbare voorbeelden zijn aangepast.

De volgende beschermde pagina's zijn ongewijzigd gebleven:

- `docs/bewerkte-lagen/afwateringseenheden.md`: de beschrijving zonder extra
  beheerderfilter past niet meer bij de standaardproductie in
  `afwateringseenheden/productie.py` en `sources.py`. RWS als bron, de drie
  doelmodi, volledige vervanging, categorievoorrang over beheerders, de
  gezamenlijke secundaire toets en de nieuwe controlelagen moeten worden
  verwerkt. De pagina noemt ook 5-km-tegels en terugknippen naar het gebied;
  de productie gebruikt 10-km-tegels en `clip_to_area=False`.
- `docs/bronlagen/index.md`: de nieuwe Rijkswaterenbron ontbreekt in de lijst.

Het #67-plan moet vóór uitvoering worden aangepast aan primaire RWS-context
en aan het onderscheid tussen branden en doelen. In #53 zijn geen
duikeruitsluitingen of herstelregels toegevoegd.
