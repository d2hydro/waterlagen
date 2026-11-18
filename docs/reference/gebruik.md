---
editorial_status: ai
---

# Waterlagen gebruiken in Python

<span id="losse-bronnen-en-bewerkingen"></span>
<span id="het-voorbeeldgebied"></span>
<span id="in-eigen-code-gebruiken"></span>
<span id="voorbeeldscripts"></span>

Kies een voorbeeldscript:

- [Een bron downloaden](bronlagen-downloaden.md), bijvoorbeeld AHN-hoogtetegels of BGT-waterdelen.
- [Een kaartlaag berekenen](bewerkte-lagen-produceren.md), bijvoorbeeld functioneel landgebruik of afwateringseenheden.

??? info "Een gedownload script uitvoeren"

    <span id="een-script-uitvoeren"></span>
    <span id="voorbereiden"></span>

    1. Sla het script op naast `pixi.toml` in het [geïnstalleerde productiepakket](../produceren/installatie.md).
    2. Open een terminal in die map en voer het script uit. Voor [download_bgt.py](voorbeelden/download_bgt.py) is de opdracht:

    ```console
    pixi run --locked python download_bgt.py
    ```

    Voor een ander script vervangt u `download_bgt.py` door de bestandsnaam.

<span id="api-referentie"></span>

Parameters, standaardwaarden en resultaten per functie vindt u in de [API-referentie](api.md).

Een standaardkaart maken zonder Python te schrijven? Gebruik de [Run Maker](../produceren/index.md).
