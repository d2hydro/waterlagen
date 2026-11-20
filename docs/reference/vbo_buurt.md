---
editorial_status: ai
---

# Woonverblijfsobjecten per CBS-buurt

Gebruik `bouw_vbo_buurt` om woonverblijfsobjecten aan CBS-buurten te koppelen. Dit is de gedeelde invoer voor [inwoners en personenauto’s](../produceren/inwoners-personenautos.md).

??? info "Woonverblijfsobjecten per buurt samenstellen · `bouw_vbo_buurt`"

    ::: waterlagen.vbo_buurt.bouw_vbo_buurt

## Verdelingen controleren

Met `waterlagen.vbo_buurt.statistiek.lees_verdelingstatistieken` vergelijkt u de berekende aantallen inwoners en auto's met de CBS-totalen. De functie telt alle buurten uit `data_store.cbs_buurt_path` mee. Gebruik voor een regionale vergelijking de CBS-totalen van dezelfde buurten als in de uitvoer.
