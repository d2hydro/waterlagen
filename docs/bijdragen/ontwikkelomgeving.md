---
editorial_status: ai
---

# Ontwikkelomgeving

Deze pagina is bedoeld voor ontwikkelaars die de broncode aanpassen of testen.
Wilt u een Waterlagen-release gebruiken om datasets te maken? Volg dan de
[installatiehandleiding voor het productiepakket](../produceren/installatie.md).
Daarvoor hoeft u Git niet te installeren.

Voor ontwikkeling: clone de repository en werk vanuit de repository-root. De projectomgeving wordt
beheerd met [pixi](https://pixi.sh/):

```bash
pixi install
```

Voer gerichte tests uit met `pixi run pytest <test-file-or-node>`. Gebruik voor
tests die PCRaster nodig hebben en voor de volledige testsuite de omgeving
`afwateringseenheden`, net als de coverage- en releaseworkflows. De belangrijkste
controles zijn:

```bash
pixi run --environment afwateringseenheden test-cov
pixi run ruff format <bestand>
pixi run ruff check <bestand>
pixi run --environment docs docs-build
```

De CI **Tests (Coverage)** draait twee testgroepen parallel: tests zonder externe
diensten en online integratietests die AHN-, BAG- en BGT-gegevens downloaden.
Beide groepen draaien bij iedere niet-concept-PR naar `main` en moeten slagen. Hun coverage wordt
samengevoegd voordat de minimale dekking van 90% wordt gecontroleerd.
De CI bewaart per groep de testtijden, JUnit-uitvoer en het geheugengebruik,
ook als een test faalt.

Gebruik lokaal dezelfde selectie met `-m "not online"` of `-m online`:

```bash
pixi run --environment afwateringseenheden pytest -m "not online" --durations=30
pixi run --environment afwateringseenheden pytest -m online --durations=30
```

Zonder deze selectie blijven alle tests meelopen. De opdracht `test-cov` blijft
de volledige suite inclusief online tests en de 90%-controle uitvoeren.

Start de lokale documentatieserver met `pixi run --environment docs docs-serve`.
De broncode staat in `src/waterlagen`, tests in `tests` en workflow-scripts in
`scripts`.
