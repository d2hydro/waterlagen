---
editorial_status: ai
---

# De BAG-indeling van een pand controleren

Met de Python-controle bekijkt u hoe een pand aan zijn landgebruiksklasse komt. De standaarduitsneden zijn Flik-Flak en Vughterstraat. Voor een andere uitsnede geeft u `bounds` mee.

```python
from waterlagen.functioneel_landgebruik.controle import main

main(overwrite=True)
```

Open `processed_data/functioneel_landgebruik/controle/bag_controle.gpkg` in QGIS. Zoek in de laag `bag_controle` op `identificatie` en lees `toelichting_resultaat`. In `uitsnede` staat bij welk voorbeeld het pand hoort. Sluit het bestand in QGIS voordat u het opnieuw maakt.

??? info "Welke kolommen horen bij welke stap?"

    | Stap | Belangrijkste kolommen |
    | --- | --- |
    | 1. Bron | `status`, `gebruiksdoel`, `bron_aantal_vbo`, `bron_vbo_overzicht` |
    | 2. Selectie | `meegenomen_stap2`, `reden_statusselectie` |
    | 3. Functie | `gekozen_pandfunctie`, `functiekeuze_status`, `reden_functiekeuze` |
    | 4. Bouwlagen | oppervlaktesom, pandoppervlakte, verhouding, bouwlagen en uitleg |
    | 5. Klasse | omschrijving, beide codes, `klasse_status`, `reden_klasse` |
    | 6. Bijzondere gebouwen | oorspronkelijke `basis_...`-klasse, bronkoppelingen, gemaalcapaciteit en uiteindelijke `reden_klasse` |

Via `stap=5` bekijkt u de oorspronkelijke BAG-klasse zonder de controle op bijzondere gebouwfuncties. De [classificatieregels](../bewerkte-lagen/functioneel-landgebruik.md#beslisboom-voor-de-gebouwfunctie) beschrijven hoe de functie en klasse worden gekozen.

## Stap 6 controleren

Vergelijk de `basis_`-kolommen met de uiteindelijke klasse en `reden_klasse`. Voor de controle van kassen, RWZI’s, drinkwaterproductielocaties en gemalen moeten de bijbehorende bronnen beschikbaar zijn. [Bronnen en selectieregels](../bewerkte-lagen/functioneel-landgebruik.md#bijzondere-gebouwen-en-gemalen-stap-6)

## Meerdere gemalen in één pand controleren

Met `waterlagen.functioneel_landgebruik.controle_gemalen.main()` controleert u de uitsnede rond gemaal Lely. Open `controle.gpkg` in `processed_data/functioneel_landgebruik/controle_gemalen_lely/`. Vergelijk `gekoppelde_gemalen` en `gemaalcapaciteit_m3_min` in `bag_controle` met de afzonderlijke capaciteiten in `gemalen_controle`.

[Terug naar functioneel landgebruik produceren](landgebruik.md)
