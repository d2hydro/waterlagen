---
editorial_status: ai
---

# Conventies

Deze afspraken gelden voor alle contributors, ongeacht of zij met of zonder AI
werken.

- Houd wijzigingen klein, leesbaar en gericht op het gevraagde gedrag.
- Inspecteer bestaande implementatie, tests en documentatie voordat gedrag wijzigt.
- Gebruik `pathlib.Path` voor paden en respecteer `overwrite=False`.
- Houd CRS, rasterresolutie, NoData en uitvoerschema's expliciet; gebruik de
  bestaande CRS- en rasterhelpers waar mogelijk.
- Gebruik in pakketcode de projectlogger en voeg gerichte tests toe bij
  gedragswijzigingen.
- Werk functionele documentatie, broninformatie en productie-instructies bij
  wanneer publiek gedrag verandert.

De minimale testdekking is 90%. Dit geldt voor lokale coverage-runs en de totale
dekking en wijzigingsdekking in Codecov.

De volledige operationele instructies voor coding agents staan in [AGENTS.md](https://github.com/d2hydro/waterlagen/blob/main/AGENTS.md).

## Python-voorbeelden en API-documentatie

De uitvoerbare voorbeelden staan op één plek: `docs/reference/voorbeelden/`.
Neem deze bestanden met `pymdownx.snippets` in de documentatie op en link naar
hetzelfde `.py`-bestand om het te downloaden. Ontbrekende snippets laten de build
falen. Kopieer de code niet naar losse Markdown-codeblokken.

Gebruik `alkmaar_centrum` waar een gebiedsselectie mogelijk is. Vermeld bij
landelijke bronnen expliciet dat ook voor dit voorbeeldgebied volledige
bestanden nodig zijn. Toon publieke bouwstenen onder de productie-API, met
instellingen bovenaan en zichtbare invoer, tussenresultaten en uitvoer.
Gebruik geen productie-ingang als enige bewerkingsstap en voeg geen onnodige
`main()`-verpakking toe. Het `__main__`-blok voorkomt uitvoering bij importeren
en ondersteunt multiprocessing. Voorbeelden hergebruiken bestaande bronnen.

API-blokken worden met `mkdocstrings` uit de functies en docstrings gegenereerd.
Ook bij `editorial_status: human` mogen deze blokken en ingelezen voorbeelden
automatisch hun bron volgen. De status beschermt de handgeschreven Markdown,
toelichting en frontmatter; hij bevriest de gegenereerde inhoud niet.
Verandert de betekenis van een functie, controleer dan ook de toelichting.
Automatische generatie ontdekt geen inhoudelijk verouderde uitleg.

Voer bij wijzigingen `pixi run pytest tests/test_python_examples.py` en
`pixi run --environment docs docs-build` uit. De voorbeeldtests starten de
scripts met nagebootste downloads en zware rasterbewerkingen die de echte
functiesignaturen controleren. De buurtselectie en inwoners-/autoberekeningen
draaien op kleine lokale GeoPackages. Controleer ook dat aangepaste instellingen
worden doorgegeven en invoer de benodigde rekenomgeving dekt.
De tests doen geen volledige productie en bewijzen geen beschikbaarheid
of inhoudelijke kwaliteit van externe bronnen. Echte downloads worden bewust
handmatig gestart; de documentatiebuild voert de voorbeelden niet uit.

Nieuwe voorbeelden krijgen een vermelding op de voorbeeldpagina en in de
testgevallen. Bij pull requests voert de workflow `Documentation checks`
deze tests en een strikte documentatiebuild uit.
