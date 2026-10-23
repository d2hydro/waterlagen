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

## Tijdelijke agent-werkdocumenten voor het samenvoegen

De statuscheck `Temporary agent work documents` controleert bij pull requests naar
`main` de volledige Git-index. Alle getrackte bestanden onder
`docs/bijdragen/implementatieplannen/` en `reviewcases/` blokkeren de check, ook
ongewijzigde bestanden, indexpagina's en Python-reproductiescripts. Er zijn geen
uitzonderingen voor bestaande bestanden. Niet-getrackte lokale bestanden blijven
buiten de controle.

De controle staat in `scripts/check_agent_workdocs.py` en werkt zelfstandig met
Python 3.11 of hoger en Git, zonder extra Python-pakketten of toegang tot andere
repositories. Voer vanuit de repositoryroot uit:

```shell
pixi run python -I scripts/check_agent_workdocs.py --repo .
```

Zonder pixi kan dezelfde opdracht met `python -I` worden uitgevoerd. Exitcode `0`
betekent dat de index schoon is; `1` meldt de blokkerende bestanden en redenen;
`2` betekent dat de controle niet kon worden voltooid. Met `--summary pad/naar/resultaat.md`
kun je ook een Markdown-samenvatting bewaren. De GitHub Action gebruikt hiervoor
`GITHUB_STEP_SUMMARY`, zodat de status, bestanden en opruiminstructie direct bij
de workflowresultaten staan.

De workflow `.github/workflows/agent-workdocs.yml` gebruikt uitsluitend de
meegeleverde controle en tests. Er zijn geen aanvullende tokens, private
downloads of configuratievariabelen nodig. De centrale bron wordt intern bij
D2hydro onderhouden; updates van de zelfstandige kopie worden als gewone
codewijziging in Waterlagen beoordeeld. Contributors kunnen de lokale kopie en
tests zelf aanpassen en uitvoeren zonder toegang tot de centrale repository.

Voer de tests met alleen Python uit:

```shell
python -B -m unittest discover -s tests -p test_check_agent_workdocs.py -v
```

Bewaar voor het samenvoegen relevante uitleg en besluiten in de reguliere
documentatie en blijvend nuttige regressietests in `tests/`. Leg resterend werk
vast in issues. Controleer eerst of plannen nog in gebruik zijn of onopgeloste
besluiten bevatten. Haal daarna alleen afgeronde werkdocumenten uit Git:
`git rm -- pad/naar/bestand` verwijdert ook de lokale kopie;
`git rm --cached -- pad/naar/bestand` behoudt die lokaal. Alleen een bestand op
schijf verwijderen of in `.gitignore` zetten haalt het niet uit de Git-index.
Neem de gestagede verwijderingen mee in de PR en voer de controle opnieuw uit.

Een beheerder kan de check `Temporary agent work documents` na een geslaagde
uitvoering verplicht maken in de branch protection rule of ruleset voor `main`.
Zonder die instelling geeft de workflow wel een foutstatus, maar blokkeert GitHub
het samenvoegen niet automatisch. De integratie wijzigt deze instellingen niet.

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
