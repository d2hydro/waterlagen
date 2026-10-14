---
editorial_status: ai
---

# Implementatieplannen afwateringseenheden

Deze plannen beschrijven **geplande, nog niet geïmplementeerde wijzigingen**.
Ze worden via een ontwerpgesprek uitgewerkt tot opdrachten voor coding agents.
De drie conceptplannen zijn uitgewerkt en liggen voor gezamenlijke eindcontrole;
start de implementatie pas nadat de plannen gezamenlijk inhoudelijk zijn bevestigd.

Deze bestanden zijn interne werkdocumenten voor agents. Ze blijven in de
repository beschikbaar en zijn uitgesloten van de gepubliceerde MkDocs-site.

## Volgorde en afzonderlijke PR's

| Volgorde | Issue | Planstatus | Voorgestelde implementatiebranch |
| --- | --- | --- | --- |
| 1 | [#65 Brandlaag](https://github.com/d2hydro/waterlagen/issues/65) | [Conceptplan; ontwerpkeuzes besproken](issue-65-brandlagen.md) | `feature/65-brandlagen` |
| 2 | [#53 Rijkswateren](https://github.com/d2hydro/waterlagen/issues/53) | [Conceptplan; ontwerpkeuzes besproken](issue-53-rijkswateren.md) | `feature/53-rijkswateren` |
| 3 | [#67 Duikers zonder eigen afwateringseenheid](https://github.com/d2hydro/waterlagen/issues/67) | [Conceptplan voor eindcontrole](issue-67-duikers.md) | `feature/67-duikers-afwateringsdoelen` |

Ieder issue krijgt een eigen implementatiebranch en PR. Rond de voorgaande PR af
voordat de volgende implementatiebranch vanaf de bijgewerkte hoofdbranch wordt
gestart. De bovenstaande branchnamen zijn voorstellen; er zijn hiermee geen
branches of PR's aangemaakt.

Issues #57, #63 en #64 vallen buiten deze reeks.

## Gezamenlijke ontwerpafspraken

- Hoogtebeïnvloeding en afwateringsdoelen blijven afzonderlijke functies. Een
  brandobject krijgt niet automatisch een eigen afwateringseenheid.
- Bij branden blijft de vaste rangorde primair > secundair > optioneel gelden.
  Een gebruikersprioriteit kan deze rangorde niet doorbreken.
- #53 gebruikt Rijkswateren uitsluitend als optionele brandlaag via #65, zonder
  eigen afwateringsdoelen. Productie van Rijkswateren-hydroobjecten uit OSM wordt
  in een ander issue uitgewerkt.
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
| Rijkswaterenlaag uit #53 | Geen nieuwe primaire geometrie | Geen nieuw doel | Optionele brandlaag, voorbeeld -200 m |

Behoud de volledige primaire bron voor de bestaande classificatie van verbonden
secundaire lijnen. Gebruik aparte selecties voor primaire brandwerking en doelen.
Filter het doelraster zonder opgeslagen segment-FIDs te hernummeren. Zo blokkeert
het brandontwerp uit #65 de duikeraanpak uit #67 niet en blijft #53 een gewone
toepassing van de optionele brandlagen.

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
