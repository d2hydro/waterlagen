---
editorial_status: ai
---

# Uitvoering #67 — Duikers en aansluitstukken

Uitgevoerd op 16 oktober 2026 op branch `67_duikers_krijgen_geen_catchments`.
Dit verslag hoort bij het [implementatieplan](issue-67-duikers.md) en blijft
samen daarmee uitgesloten van de documentatiesite.

## Implementatie

- De gerichte duikerlezer bewaart geometrie, oorspronkelijke identifiers,
  bronbestand, bronlaag en FID. De productie vereist de GKW-duikerlaag en bij
  eigen levering ook de eigen duikerlaag. Lege lagen zijn geldig. Eigen levering
  vervangt alle objecten van de beheerder, ook buiten de doelcontext.
- GKW-duikers met code `80` zijn uitgesloten. De optionele RWS-duikerlaag is de
  enige RWS-duikerbron. Een aanwezige laag wordt volledig op identifiers en CRS
  gecontroleerd. De eigen levering wordt eveneens vóór ruimtelijke selectie
  en AHN-voorbereiding gevalideerd.
- Koppeling gebeurt eenmaal tegen de volledige primaire context. De geometrie
  bepaalt een route over bestaande lijnaansluitingen; gedeelde knooppunten
  worden als één kandidaatlocatie behandeld. De endpointafstand is inclusief
  0,5 m. Beheerdergelijkheid en kortste netwerkafstand geven geen doorslag.
- De bron blijft beschikbaar voor de gezamenlijke secundaire toets. De
  afzonderlijke brandlaag bevat geen gekoppelde duikertrajecten. De volledige
  segmentlaag bewaart brand- en doelgeschiktheid en duikerherkomst. Ook
  uitgesloten contexttrajecten van niet-deelnemende beheerders blijven zichtbaar.
- Directe aansluitstukken worden vóór maximumlengtesplitsing geclassificeerd.
  `None` behoudt alle aansluitdoelen; een eindige, niet-negatieve grens sluit
  alleen directe stukken tot en met die lengte uit. Hun primaire brandwerking
  blijft behouden. De doelrasterisatie behoudt opgeslagen FIDs bij filtering.
- `controle.gpkg`, laag `duikersifonhevel`, bevat afzonderlijke mislukte
  koppelingen. Geen enkele mislukte koppeling veroorzaakt een gedeeltelijke
  ingreep. De laag wordt atomisch vervangen, ook als zij leeg is, met behoud
  van andere controlelagen. Hervatten herstelt ontbrekende controle-uitvoer.
- Productie en CLI bieden `duiker_tolerance` / `--duiker-tolerance` en
  `max_aansluitlengte` / `--max-aansluitlengte`. Runmetadata bevat beleid,
  bronlagen, RWS-aanwezigheid en parameters. Bronidentiteiten inclusief WAL
  worden gevolgd. Gewijzigde productie-invoer vereist een nieuwe run-ID.
- Lagere functies vernieuwen ongeschikte snapshots ook bij `overwrite=False`.
  De snapshotidentiteit voedt de bestaande raster- en tegelidentiteiten;
  workers ontvangen het voorbereide bestand en koppelen geen duikers opnieuw.

De routezoeker accepteert routes die langs de duikerprojectie voortgaan.
Bij meerdere kandidaten bepaalt de geometrische Hausdorff-afstand de keuze;
gelijke scores gaan naar controle. Niet-monotone routes worden conservatief
niet gekoppeld. Meer dan 128 routes of 10.000 zoekstappen leveren een
ambiguïteitsmelding op. Deze keuzes en beperkingen zijn in de API-reference
gedocumenteerd. Er wordt geen strookbuffer of ondergrondse stroomroute gemaakt.

## Technische verificatie

De betrokken watersysteem-, bron-, raster-, PCRaster-, tegel-, worker-,
productie-, CLI-, GeoPackage- en voorbeeldtests zijn uitgevoerd in de pixi-omgeving
`afwateringseenheden`: **279 geslaagd**. De gerichte regressies behandelen onder meer:

- binnen/op/buiten de endpointgrens, omgekeerde tekenrichting, meerdere
  bronobjecten, parallelle lijnen, kruisingen, bron- en beheerdergrenzen;
- geen, halve en onduidelijke koppelingen; onbruikbare geometrie en
  overlappende duikers met behoud van alle duikeridentiteiten;
- directe vertakkingen, fysieke puntgrenzen, geen recursieve selectie en
  gelijkblijvende lengteclassificatie bij gewijzigde maximumsegmentlengte;
- ongewijzigde secundaire brandwerking, optionele brandwerking, FID-gaten en
  de FID-naar-segment-ID-koppeling in echte PCRaster-berekeningen;
- identieke seriële/parallelle uitvoer bij tegelranden, geen verdubbelde
  controles, lege tegeluitvoer en behoud van beide controlelocaties;
- eigen vervanging, ontbrekende verplichte lagen, lege en later toegevoegde
  RWS-lagen, bron-CRS-selectie, identifiers buiten de selectie en WAL-wijzigingen;
- hergebruik, ontbrekende controle-uitvoer, oude snapshots zonder metadata,
  gewijzigde bronnen/instellingen/controleobjecten en uitschakelen van duikerinvoer.

Gewijzigde Python wordt met Ruff gecontroleerd en geformatteerd. De strikte
MkDocs-build is geslaagd. Er is gecontroleerd dat implementatieplannen en dit
verslag ontbreken in zowel de gegenereerde pagina's als de zoekindex.
De beschermde functionele Markdown is niet gewijzigd.
De bestaande rasterio/Affine-deprecatiewaarschuwingen staan los van deze wijziging.

## Lokale broncontrole bij de issuecoördinaat

Er is offline gerekend met de bestaande datastore `2026.9.1`, zonder downloads
of wijziging van de grote bronbestanden. De bronbestanden zijn `hydamo.gpkg`
(4.557.549.568 bytes), `rws_hydamo.gpkg` (872.448 bytes) en de bestaande
`dtm_05.vrt`. De RWS-bron bevat geen duikerlaag.

De vergelijking is een lokale technische proef, geen volledige
Aa-en-Maas-productie of inhoudelijke goedkeuring. Rekenextent:
`(179400, 406000, 180000, 406600)`, 2 m resolutie; vectorcontext met 500 m extra
buffer. Beheerder `38`, koppeltolerantie 0,5 m, netwerktolerantie 2 m,
maximumsegmentlengte 500 m, branddiepte 100 m, opvuldiepte 50 m en PCRaster-seed
12345. De context bevat 25 primaire lijnen, 2 secundaire lijnen en 27 duikers.
Alle 27 duikers koppelen; beide controlebestanden bevatten een geldige lege laag.

Bij `(179684.380, 406253.726)` gaat het om GKW-duiker `1070175`,
`NL.WBHCODE.38.Duikersifonhevel.2786`, FID `509682`, globalid
`{24A00690-6B57-4BE8-BBA6-16D9AECE44C5}`. Het gekoppelde primaire bronobject
heeft FID `1248641` en globalid `{6B99A7E4-AD38-465D-AA40-4490ADFF7A91}`.
Het duikertraject meet 28,2753 m; de directe aansluitstukken meten 9,6933 en
6,8136 m. De grens 50 m selecteert beide aansluitstukken.

| Variant | Segmenten in context | Afwateringseenheden in rekenextent | Gewijzigde DEM-cellen t.o.v. zonder ingreep |
| --- | ---: | ---: | ---: |
| Zonder duikerinvoer | 35 | 7 | 0 |
| Duikers, aansluitgrens `None` | 87 | 11 | 19 |
| Duikers, aansluitgrens 50 m | 87 | 9 | 19 |

Bij duikerbewerking veranderen 2.318 LDD-cellen ten opzichte van de variant
zonder ingreep. De DEM- en LDD-rasters van `None` en 50 m zijn identiek.
Alle drie lokale varianten kennen de 360.000 m² rekenextent toe. Dit bewijst
geen juistheid van de toekenning buiten deze kleine proef.

Lokale, door Git genegeerde bestanden staan onder `data/issue67/`:

- `inspect_local.py`: reproduceerbare offline vergelijking;
- `comparison.json`: bronidentiteiten, VRT-afhankelijkheden, parameters en
  segmentgegevens bij de issuecoördinaat;
- `comparison.png`: technische kaartvergelijking van knipgrenzen, brand- en
  doelgeometrie, afwateringseenheden en stroomrichtingen;
- `without/`, `standard/`, `adjacent_50m/`: GeoPackages, DEM, doelraster,
  LDD en subcatchments; de twee duikervarianten hebben `controle.gpkg`;
- `sources.gpkg`: geselecteerde primaire bronlijnen en oorspronkelijke duikers.

De kaart is technisch bekeken: het duikertraject onderbreekt de primaire
brandstrook; de korte aansluitstukken blijven branden en verliezen bij 50 m
hun doelstatus. Andere watergangen blijven zichtbaar. Rastercellen aan
duikergrenzen kunnen nog door toegestane aangrenzende geometrie geraakt worden.
Menselijke beoordeling in QGIS en inhoudelijke acceptatie blijven nodig.

## Documentatiebevindingen en resterende acceptatie

Documentatie-impact: **confirmed**. Productie-instructies, HYDAMO- en
RWS-bronpagina's, API-reference en het uitvoerbare Python-voorbeeld zijn bijgewerkt.

De beschermde pagina [Afwateringseenheden](../../bewerkte-lagen/afwateringseenheden.md)
vereist menselijke aanvullingen, maar is niet aangepast:

- Bij de vectorvoorbereiding ontbreken duikerknippen, controleobjecten en de
  afzonderlijke geschiktheid van duikertrajecten en directe aansluitstukken.
- De tekst over branden en doelrasterisatie moet de uitsluiting en het behoud
  van secundaire/optionele brandwerking uitleggen; niet alle primaire segmenten
  zijn nog doelen. Relevant: `workflow.py:prepare_watersysteem`,
  `workflow.py:write_watersysteem` en `raster.py:_segment_raster`.
- Bij de uitvoer ontbreken de volledige primaire bron, alle geknipte context,
  geschiktheidskolommen en `controle.gpkg`. Een voltooide run kan controleobjecten
  bevatten. De bestaande punten over doelmodi en knippen aan gebiedsgrenzen
  behoeven daarnaast nog de al bij #53 gemelde correcties.
- De stellige beschrijving van stroomtoekenning moet worden beoordeeld in het
  licht van de gewijzigde doelen en mogelijke onverdeelde gebieden. De code
  voegt geen ondergrondse duikerverbinding toe en forceert geen buurtoekenning.

De volledige inhoudelijke Aa-en-Maas-vergelijking uit #53 en menselijke
kaartbeoordeling zijn hiermee niet afgerond. Er is geen PR geaccepteerd of
samengevoegd; de wijzigingen staan lokaal op de issuebranch.
