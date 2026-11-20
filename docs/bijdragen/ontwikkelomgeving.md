---
editorial_status: ai
---

# Ontwikkelomgeving

Installeer [Pixi](https://pixi.sh/) en open een terminal. Haal de code op en installeer de projectomgeving.

```bash
git clone https://github.com/d2hydro/waterlagen.git
cd waterlagen
pixi install
```

## Uw wijziging controleren

| Taak | Opdracht |
| --- | --- |
| Eén testbestand draaien | `pixi run pytest tests/test_python_examples.py` |
| Python-code opmaken | `pixi run ruff format <bestand>` |
| Python-code controleren | `pixi run ruff check <bestand>` |
| Handleiding bekijken | `pixi run --environment docs docs-serve` |
| Handleiding controleren | `pixi run --environment docs docs-build` |

Vervang bij het testen het voorbeeldpad door uw testbestand. Gebruik voor tests met PCRaster `pixi run --environment afwateringseenheden pytest <testbestand>`.

Voor de Run Maker-bedieningstest hebt u Node.js nodig. Installeer de testpakketten met `npm ci --prefix tests/browser` en voer `pixi run pytest tests/test_runscript_dom.py` uit.

De volledige testsuite met dekkingscontrole draait met `pixi run --environment afwateringseenheden test-cov`.

Bij een pull request naar `main` draaien de offline en online tests zodra de PR klaar is voor beoordeling. Lokaal kiest u met `pytest -m "not online"` of `pytest -m online` dezelfde groepen. De online tests downloaden AHN-, BAG- en BGT-gegevens.

Werkt u aan parallel rekenen? Zie [tests en meetresultaten voor afwateringseenheden](afwateringseenheden-scaling.md).
