# Ontwikkelomgeving

Kloon de repository en werk vanuit de repository-root. De projectomgeving wordt
beheerd met [pixi](https://pixi.sh/):

```bash
pixi install
```

Voer gerichte tests uit met `pixi run pytest <test-file-or-node>`. De belangrijkste
controles zijn:

```bash
pixi run test-cov
pixi run ruff format <bestand>
pixi run ruff check <bestand>
pixi run --environment docs docs-build
```

Start de lokale documentatieserver met `pixi run --environment docs docs-serve`.
De broncode staat in `src/waterlagen`, tests in `tests` en workflow-scripts in
`scripts`.
