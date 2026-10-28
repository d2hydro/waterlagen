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

Start de lokale documentatieserver met `pixi run --environment docs docs-serve`.
De broncode staat in `src/waterlagen`, tests in `tests` en workflow-scripts in
`scripts`.
