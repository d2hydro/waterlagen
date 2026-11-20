---
editorial_status: ai
---

# Afspraken voor code en documentatie

## Code wijzigen

- Bekijk eerst de bestaande code en tests. Houd de wijziging bij één onderwerp.
- Gebruik `pathlib.Path` voor bestandspaden, respecteer `overwrite=False` en log via de projectlogger.
- Maak CRS, rasterresolutie, NoData en uitvoerschema expliciet. Hergebruik de CRS- en rasterhelpers.
- Test gewijzigd gedrag. De minimale testdekking is 90%, zowel voor het geheel als voor gewijzigde code in Codecov.

Gebruikt u een AI-assistent? [Geef de projectinstructies mee](ai-agents.md).

## Documentatie bijwerken

Werk de betreffende bronpagina, laagbeschrijving of productie-instructie bij wanneer de werking verandert. De API-referentie haalt parameters en resultaten uit de docstrings.

??? info "Een Python-voorbeeld toevoegen"

    Zet het script in `docs/reference/voorbeelden/`. Neem het met `pymdownx.snippets` op in de voorbeeldpagina en link naar hetzelfde bestand als download.

    Zet de instellingen bovenaan en toon de publieke functies voor invoer, bewerking en uitvoer. Hergebruik bestaande bronbestanden. Gebruik waar mogelijk `alkmaar_centrum` en vermeld wanneer een landelijke download nodig is. Bescherm de uitvoering met `if __name__ == "__main__":` voor import en multiprocessing.

    Voeg een offline test toe aan `tests/test_python_examples.py`. Draai dat testbestand en bouw de handleiding. Controleer ook de begeleidende tekst bij gewijzigde functies. Op menselijk beheerde pagina’s volgen alleen gegenereerde API-blokken en ingelezen voorbeelden automatisch hun bron.

## Vóór het samenvoegen

De GitHub-controle `Temporary dev work documents` vereist bij een pull request naar `main` dat er geen bestanden uit `dev-workdocs/` in de Git-index staan.

??? info "Werkdocumenten controleren en lokaal bewaren"

    Bewaar tijdelijke reviews en reproductiescripts onder `dev-workdocs/reviews/` en plannen onder `dev-workdocs/implementatieplannen/`. Neem blijvende uitleg op in `docs/`, regressietests in `tests/` en openstaande punten in issues.

    Controleer welke documenten nog in gebruik zijn. Haal alleen afgeronde bestanden uit Git met `git rm --cached -- <bestand>` om de lokale kopie te behouden. Neem de verwijdering uit Git mee in de pull request.

    ```bash
    pixi run python -I scripts/check_dev_workdocs.py --repo .
    ```
