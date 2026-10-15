---
editorial_status: ai
---

# Implementatieplannen afwateringseenheden

Deze plannen leggen de ontwerpafspraken en opdrachten voor coding agents vast.
#65 is op verzoek geïmplementeerd en ligt ter review. Het verruimde ontwerp voor
#53 is na grilling bevestigd op 15 oktober 2026; alleen het plan is bijgewerkt.
#53 en #67 beschrijven geplande wijzigingen, geen beschikbare implementaties.

Deze bestanden zijn interne werkdocumenten voor agents. Ze blijven in de
repository beschikbaar en zijn uitgesloten van de gepubliceerde MkDocs-site.

## Volgorde en afzonderlijke PR's

| Volgorde | Issue | Planstatus | Voorgestelde implementatiebranch |
| --- | --- | --- | --- |
| 1 | [#65 Brandlaag](https://github.com/d2hydro/waterlagen/issues/65) | [Geïmplementeerd; PR #79 ter review](issue-65-brandlagen.md) | `issue/65_brandlagen` |
| 2 | [#53 Rijkswateren en omringende brandcontext](https://github.com/d2hydro/waterlagen/issues/53) | [Verruimd ontwerp bevestigd; nog niet geïmplementeerd](issue-53-rijkswateren.md) | `issue/53_opname_rijkswateren` |
| 3 | [#67 Duikers zonder eigen afwateringseenheid](https://github.com/d2hydro/waterlagen/issues/67) | [Conceptplan voor eindcontrole](issue-67-duikers.md) | `feature/67-duikers-afwateringsdoelen` |

Ieder issue krijgt een eigen implementatiebranch en PR. Rond de voorgaande PR af
voordat de volgende implementatiebranch vanaf de bijgewerkte hoofdbranch wordt
gestart. Voor #65 bestaat [PR #79](https://github.com/d2hydro/waterlagen/pull/79).
Het #53-plan is bijgewerkt op `issue/53_opname_rijkswateren`, met de #65-code
al aanwezig. Dit geeft nog geen opdracht tot implementatie. De branchnaam voor
#67 blijft een voorstel.

Issues #57, #63 en #64 vallen buiten deze reeks.

## Vrije gebiedsselectie

Voor [#63 Testgebieden](https://github.com/d2hydro/waterlagen/issues/63) is een
[implementatieplan voor vrije gebiedsselectie](issue-63-bounds.md) opgesteld.
Het voegt gedeelde CLI-bounds en een PowerShell-voorbeeld voor gebruik met
QGIS-brandlagen toe. De implementatie is nog niet gestart. Dit plan staat los
van bovenstaande PR-volgorde en introduceert geen gebruikstestframework.

## Gezamenlijke ontwerpafspraken

- Hoogtebeïnvloeding en afwateringsdoelen blijven afzonderlijke functies. Een
  brandobject krijgt niet automatisch een eigen afwateringseenheid.
- Bij branden blijft de vaste rangorde primair > secundair > optioneel gelden.
  Een gebruikersprioriteit kan deze rangorde niet doorbreken.
- #53 scheidt bronselectie, brandcontext en afwateringsdoelen. Een eigen
  GeoPackage vervangt alle GKW-objecten van het gekozen waterschap. Een vlag
  bepaalt of overige waterschappen ook doelen leveren; hun brandwerking blijft.
  Rijkswateren leveren bij een gekozen waterschap uitsluitend brandcontext en
  zonder gekozen waterschap ook primaire afwateringsdoelen, zelfs bij een kleine
  geografische uitsnede. #53 hergebruikt #65 met expliciete brandcategorieën.
  Automatische productie van Rijkswateren-hydroobjecten uit OSM blijft buiten scope.
- Classificeer in #53 alle secundaire lijnen gezamenlijk tegen alle geselecteerde
  primaire lijnen, ongeacht deelname als doel. Alleen verbonden groepen worden
  gebrand; uitgesloten lijnen en niet-toegewezen gebieden blijven zichtbaar voor
  controle. De categorie, niet de beheerder, bepaalt de brandvoorrang.
- #67 knipt alleen primaire hydroobjecten bij duikers, sifons en hevels.
  Duikertrajecten krijgen geen primaire brandwerking en geen afwateringsdoel.
  Directe aansluitstukken tot een instelbare lengte blijven branden maar verliezen
  hun doel; standaard `None` laat deze aansluitstukken ongemoeid. Secundaire en
  optionele brandlagen blijven werken, ook op duikertrajecten. De standaard
  koppeltolerantie is 0,5 m voor ieder duikeruiteinde. Niet goed gekoppelde
  duikers worden met reden naar `controle.gpkg` geschreven; de verwerking gaat
  door met een waarschuwing en zonder gedeeltelijke ingreep voor die duikers.
- Houd bronidentiteit, segmentidentiteit en GeoPackage-FID uit elkaar.
- Gewijzigde bronnen of instellingen moeten doorwerken in de controle op
  hergebruik van watersysteem, rasters en daarvan afgeleide tegelresultaten.

## Samenhang voor implementerende agents

| Geval | Primaire brandwerking | Afwateringsdoel | Secundaire/optionele brandwerking |
| --- | --- | --- | --- |
| Gewoon primair traject | Behouden | Behouden | Bestaande rangorde |
| Correct gekoppeld duikertraject | Uitgesloten | Uitgesloten | Blijft toegestaan |
| Direct aansluitstuk <= ingestelde lengtegrens | Behouden | Uitgesloten | Bestaande rangorde |
| Aansluitstuk bij `None` of boven de lengtegrens | Behouden | Behouden | Bestaande rangorde |
| Niet goed gekoppelde duiker | Gewone verwerking behouden | Gewone verwerking behouden | Bestaande rangorde; duiker naar controlebestand |
| Rijkswateren uit #53, waterschap gekozen | Primaire categorie, gekoppeld aan branddiepte | Geen nieuw doel | Gezamenlijke secundaire verbindingstoets; gewone optionele lagen blijven ondergeschikt |
| Rijkswateren uit #53, geen waterschap gekozen | Primaire categorie, gekoppeld aan branddiepte | Primaire RWS-segmenten | Dezelfde categorievolgorde en verbindingstoets |

Behoud de volledige primaire bron voor de bestaande classificatie van verbonden
secundaire lijnen. Gebruik aparte selecties voor primaire brandwerking en doelen.
Filter het doelraster zonder opgeslagen segment-FIDs te hernummeren. #53 breidt
de voorbereiding uit met categoriegestuurde brandcontext, terwijl gewone
optionele lagen hun #65-contract behouden.

De #67-tekst gaat nog uit van het oude #53-ontwerp: Rijkswateren als gewone
optionele laag zonder doelen. Verzoen die aanname vóór implementatie van #67
met de nieuwe primaire brandcategorie en de doelmodi. Herstel uitgesloten
primaire duikertrajecten niet via een tweede, ongefilterde brandcontext.

## Uitvoering en documentatie

Volg [de contributorconventies](../conventions.md) en de operationele instructies
in het repositorybestand `AGENTS.md`. Elk definitief plan moet scope, interfaces,
implementatiestappen, tests, documentatie en acceptatiecriteria bevatten.

Documentatie-impact: **confirmed**. Deze plannen zijn nieuwe interne
werkdocumenten. De toekomstige implementaties veranderen bovendien het
gedrag dat in de functionele documentatie wordt beschreven.

De pagina [Afwateringseenheden](../../bewerkte-lagen/afwateringseenheden.md)
heeft `editorial_status: human`. De plannen verlenen geen toestemming om die
pagina te wijzigen. Rapporteer noodzakelijke inhoudelijke aanvullingen afzonderlijk;
werk bewerkbare productie- en API-documentatie bij binnen de betreffende PR.
