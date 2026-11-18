---
editorial_status: ai
---

# Eigen landgebruikscodes gebruiken

Maak een kopie van de meegeleverde codetabel:

```python
from pathlib import Path
from shutil import copyfile
from waterlagen.functioneel_landgebruik.landgebruikstabel import DEFAULT_MAPPING_CSV

copyfile(DEFAULT_MAPPING_CSV, Path("mijn_landgebruik.csv"))
```

Kies de kopie in de Run Maker bij **Eigen landgebruikscodetabel (.csv)**. De gebruikte CSV wordt bij de kaart bewaard.

## Bewerken in Excel

1. Pas de binnendijkse en buitendijkse codes en de klassebeschrijvingen aan. Gebruik codes van 1 t/m 255. De twee reeksen mogen elkaar niet overlappen. Code 0 is NoData.
2. Sla op als **CSV in UTF-8 met puntkomma’s**. Komma’s kunnen deel uitmaken van een bronwaarde.
3. Kies een nieuwe runnaam zodra u de CSV wijzigt. Hervatten vereist een byte voor byte gelijke tabel.

??? info "Welke kolommen en bronwaarden kan ik aanpassen?"

    | Kolom | Gebruik |
    | --- | --- |
    | `Koppelmethode` | `mapping` voor een directe bronwaarde; `functie` voor een ingebouwde Python-regel. |
    | `Koppel-ID` | Verplicht en vast voor `functie`; mag leeg blijven voor `mapping`. |
    | `Bron`, `Bronlaag`, `Bronveld` | Ondersteunde bron, laag en attribuut voor directe koppelingen. Bij functies beschrijven ze de invoer; de BAG-identiteit wordt gecontroleerd. |
    | `Bronwaarde` | Precies één volledige waarde per rij, of `*` als vangnet. |
    | `LGB-code_binnendijks`, `LGB-code_buitendijks` | Respectievelijk de standaardcode en de buitendijkse code, bewerkbaar van 1 t/m 255; 0 blijft NoData. De twee codereeksen mogen niet overlappen. |
    | `LGB_beschrijving` | Bewerkbare klassenaam voor uitvoer en legenda. Dezelfde standaardcode vereist dezelfde beschrijving. |
    | `Toelichting` | Optionele vrije tekst, zonder invloed op verwerking. |
    | `Documentatie` | Optionele documentatie-URL; wordt tijdens verwerking niet opgehaald. |

    Pas normaal de twee codes en de beschrijving aan. Kopieer voor een nieuwe
    directe koppeling een `mapping`-rij uit dezelfde bronlaag, laat `Koppel-ID` leeg
    en vul één nieuwe bronwaarde in. Herhaal een doelcode gerust voor meerdere
    bronwaarden, met een consistente beschrijving. Dubbele bronwaarden binnen
    dezelfde bronlaag zijn niet toegestaan, ook niet bij gelijke uitvoercodes.

    **Let op (!)**. Bij regels met `Koppelmethode == functie` kun je alleen de `LGB-code_binnendijks`, `LGB-code_buitendijks`, `LGB_beschrijving`, `Toelichting` en `Documentatie` aanpassen.

    De functie zelf ligt vast in de software en wordt herkend via Koppel-ID. Je kunt via de CSV dus geen nieuwe Python-functies of nieuwe rekenregels toevoegen.

    Houd bij het aanpassen van codes rekening met
    [overlap en rastervoorrang](../bewerkte-lagen/functioneel-landgebruik.md#overlap-en-rastervoorrang).
    CSV-rijvolgorde en codehoogte bepalen niet welke bron bij overlap wint.
    Bij aangepaste codetabellen geldt een uitzondering op de
    [conflictregel voor bijzondere gebouwen](../bewerkte-lagen/functioneel-landgebruik.md#conflicten-tussen-bijzondere-gebouwregels):

    - Meerdere passende kas-, RWZI- of drinkwaterregels mogen dezelfde klasse opleveren. Zowel de standaardcodes als de buitendijkse codes moeten overeenkomen.
    - Verschillen de codeparen, dan krijgt het pand NoData. Ook de eerder bepaalde BAG-klasse vervalt.
    - Een gekoppeld gemaal samen met een andere bijzondere gebouwfunctie blijft een conflict. Ook bij gelijke codeparen krijgt het pand NoData.

    De ondersteunde directe combinaties zijn:

    | Bron | Bronlaag | Bronveld |
    | --- | --- | --- |
    | BRP | `brp_gewas` | `gewascode` |
    | TOP10NL | `top10nl_functioneel_gebied_vlak`, `top10nl_functioneel_gebied_multivlak` | `typefunctioneelgebied` |
    | BGT | `bgt_wegdeel`, `bgt_ondersteunendwegdeel` | `bgt-functie` |
    | BGT | `bgt_begroeidterreindeel` | `bgt-fysiekVoorkomen` |
    | BGT | `bgt_onbegroeidterreindeel`, `bgt_waterdeel` | Leeg, uitsluitend `*` |

    Een willekeurige nieuwe bron, laag of attribuut kan niet alleen door een CSV-rij
    worden toegevoegd. Niet-ondersteunde combinaties geven een foutmelding.

    `*` vangt geldige bronwaarden op waarvoor geen expliciete koppeling bestaat.
    Expliciete waarden gaan altijd voor, ongeacht de rijvolgorde. Lege waarden,
    witruimte en ontbrekende waarden vallen hierbuiten. Voor BRP moet de
    waarde bovendien een positief geheel getal zijn. Een leeg `Bronveld` betekent
    geen attribuutfilter: alle verder geschikte objecten worden gekoppeld. Dit is
    alleen ondersteund voor de twee genoemde BGT-lagen en vereist `Bronwaarde = *`.
    Zie ook de [functionele verwerking](../bewerkte-lagen/functioneel-landgebruik.md#codes-uit-de-csv).

[Terug naar functioneel landgebruik produceren](landgebruik.md)
