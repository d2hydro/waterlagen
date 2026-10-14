---
editorial_status: ai
---

# #67 — Duikers en aansluitstukken

**Status:** conceptplan voor gezamenlijke eindcontrole. De functionele keuzes
zijn in het ontwerpgesprek besproken. Dit document beschrijft gepland gedrag,
geen reeds beschikbare functionaliteit.

Issue: [#67 Duikers hebben geen eigen afwateringseenheid](https://github.com/d2hydro/waterlagen/issues/67).
Uitvoering: derde afzonderlijke branch en PR uit het
[gezamenlijke overzicht](index.md), na #65 en #53.

## Doel en scope

Alleen primaire hydroobjecten worden bij duikers, sifons en hevels opgeknipt,
op de aan de primaire lijnen gekoppelde uiteinden. Het tussenliggende
duikertraject krijgt geen primaire brandbewerking en geen eigen
uitstroompunt/afwateringsdoel. Bewaar het traject herkenbaar in de vectorgegevens
voor controle. Secundaire hydroobjecten worden door deze ingreep niet gewijzigd.

Direct aan een duiker grenzende stukken met lengte kleiner dan of gelijk aan
een instelbare grens kunnen worden uitgesloten als afwateringsdoel. Meet de
lengte na knippen op duikers en bestaande objectgrenzen, vóór de gewone opdeling
in maximale segmentlengtes. Loop niet recursief door een keten van korte stukken.
Deze aansluitstukken behouden hun primaire brandwerking.

De standaard is `None`: dan wordt geen extra aansluitstuk uitgesloten. Dit
schakelt niet de knipregel of uitsluiting van het duikertraject zelf uit.

De ingreep is geen absoluut brandverbod op rastercellen. Optionele brandlagen
uit #65, inclusief Rijkswateren uit #53, mogen op het duikertraject blijven
werken. Ook een daar overlappende secundaire lijn behoudt haar brandwerking.
De vaste rangorde geldt voor de brandgeometrie die na selectie overblijft.

## Relevante bestaande werking

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

Gebruik de objectlaag `duikersifonhevel` uit de bestaande HYDAMO-bron. Controleer
het daadwerkelijk aangeleverde schema en bruikbare bronrelaties vóór implementatie
van de inleesfunctie. Er is lokaal nog geen bronbestand beschikbaar waarmee de
objecten rond de issuecoördinaat zijn geverifieerd. Maak daarom geen ongetoetste
aanname over een specifiek relatieattribuut.

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
staat dit bestand in de betreffende productierun. Bewaar minimaal bronbestand,
bronlaag, oorspronkelijke FID, beschikbare bron-ID en `reden`. Voeg waar
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
correct gekoppelde objecten. Een lege controlelaag is een geldig resultaat;
preserveer eventueel aanwezige andere controlelagen. Bij hergebruik moet ook
het bijbehorende controlebestand beschikbaar blijven.

Deze doorwerkregel betreft objecten die niet goed koppelen. Technische fouten
waardoor de bron niet kan worden gelezen of de uitvoer niet kan worden geschreven
blijven gewone fouten; ze mogen niet als een succesvolle berekening met nul
duikers worden gepresenteerd. Een aanwezige lege bronlaag is wel geldig.

## Brandgeometrie, netwerk en afwateringsdoelen

Bewaar de volledige primaire brongeometrie voor de bestaande classificatie
van verbonden secundaire waterlopen. `write_watersysteem` gebruikt die primaire
geometrie namelijk ook om secundaire verbindingen vast te stellen. Daar duiker-
trajecten verwijderen zou onbedoeld de secundaire brandwerking veranderen.

Maak daarom voor het branden een afzonderlijke selectie van primaire geometrie
zonder de correct gekoppelde duikertrajecten. Bewaar de volledige segmentlaag
met expliciete geschiktheid voor branden en afwateringsdoelen, plus herkomst
van de duikerselectie. Geen nieuwe generieke beleidsengine is nodig.

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
leest de duikerlaag uit dezelfde HYDAMO-bron als de andere waterobjecten.
Maak tolerantie en aansluitlengte instelbaar via de normale productie-ingang
en CLI. Gebruik hiervoor gewone productspecifieke opties; breid de
brandlagen-TOML uit #65 niet uit met netwerkbewerkingen.

Verwerk de duikerbron, tolerantie, aansluitlengte en beleidsversie in de
productiemetadata en de controle op hergebruik. Controleer drie niveaus:

1. Het voorbereide watersysteem en de segmentclassificatie.
2. DEM en afwateringsdoelraster.
3. Afgeleide tegelresultaten en hun samenvoeging.

Een geldig GeoPackage-schema of gelijk rastergrid is onvoldoende bewijs dat
de oude uitvoer bij de nieuwe duikerselectie hoort. Ook wijzigingen aan de
controleobjecten moeten bij herberekening worden verwerkt. Hergebruik blijft
mogelijk bij ongewijzigde invoer; herdownload geen onaangetaste grote bronnen.

## Implementatiestappen

1. Inspecteer het bronlaagcontract en voeg een gerichte lezer voor
   `duikersifonhevel` toe. Hergebruik de GeoPandas-wrapper, CRS-helpers en
   correcte ruimtelijke selectie in bron-CRS; behoud bron-FIDs en bron-ID's.
2. Voeg koppelen, geprojecteerde splitsposities en classificatie toe in de
   watersysteemvoorbereiding. Scheid duikerknippen van de bestaande logica
   voor verbindende puntobjecten. Houd mislukte koppelingen apart als
   controleobjecten.
3. Bewaar volledige brongeometrie, segmentherkomst en afzonderlijke
   geschiktheid voor primaire brandwerking en afwateringsdoelen.
4. Breid de primaire brandselectie en doelrasterisatie uit, zonder secundaire
   of optionele brandregels te veranderen. Bewaak de FID-koppeling.
5. Schrijf `controle.gpkg`, verbind parameters aan productie/CLI en geef de
   bestaande tegelverwerking de voorbereide gegevens door. Herhaal het
   volledige duikerkoppelproces niet per worker.
6. Werk de controle op hergebruik bij op watersysteem-, raster- en tegelniveau.
7. Voeg tests, publieke NumPy-docstrings, productie-instructies en een
   uitvoerbaar Python-voorbeeld met duikerinvoer en controle-uitvoer toe.

## Technische acceptatiecriteria

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
  controleobjecten over. De waarschuwing noemt aantal en uitvoerpad.
- `None` behoudt alle aansluitdoelen; met een grens worden alleen directe
  stukken van lengte <= die grens uitgesloten. Test korter, gelijk en langer,
  een vertakking en een keten van korte stukken.
- Aansluitstukken blijven primair branden, ook als ze geen doelen meer zijn.
- Een gewone korte watergang zonder duiker verliest zijn doel niet.
- Secundaire classificatie en brandwerking blijven gelijk, inclusief een
  secundaire lijn die alleen nabij een uitgesloten duikertraject aansluit.
- Optionele brandlagen kunnen op duikertrajecten blijven werken. Test de
  combinatie met de Rijkswaterenconfiguratie uit #53.
- FID-naar-segment-ID-koppeling blijft juist wanneer tussen twee toegestane
  doelen een uitgesloten segment staat.
- Seriële/parallelle verwerking en duikers bij tegelranden leveren dezelfde
  classificatie op; controleobjecten worden niet per tegel gedupliceerd.
- Gewijzigde bron, tolerantie of lengtegrens maakt alle afhankelijke caches
  ongeldig; ongewijzigde invoer blijft herbruikbaar.

Gebruik kleine synthetische GeoPackages en rasters, zonder netwerkverkeer.
Werk gerichte tests bij voor watersysteem, rasters, subcatchments, tegels,
workers, productie en voorbeelden. Voer ze uit met
`pixi run pytest <test-bestanden>`. Controleer gewijzigde Python met Ruff,
voer voor het voorbeeld `pixi run pytest tests/test_python_examples.py` uit
en bouw met `pixi run --environment docs docs-build`.

## Afhankelijkheden en verificatie

Behoud in #65 afzonderlijke selectie voor vaste brandgeometrie, optionele
brandobjecten en afwateringsdoelen. De hoogteprioriteiten uit #65 worden niet
door de lengte-instelling van #67 vervangen.

#53 levert uitsluitend optionele Rijkswateren-brandobjecten, zonder nieuwe
afwateringsdoelen. Deze optionele geometrie blijft ook op duikertrajecten
toegestaan; er komt geen Rijkswateren-specifieke uitzondering.

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
Werk de bewerkbare productie-instructies, HYDAMO-bronbeschrijving waar relevant,
API-referentie en voorbeelden bij. Documenteer nadrukkelijk dat een voltooide
run nog controleobjecten kan bevatten en hoe die in QGIS worden beoordeeld.
