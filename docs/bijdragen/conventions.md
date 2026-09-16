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

De volledige operationele instructies voor coding agents staan in [AGENTS.md](https://github.com/d2hydro/waterlagen/blob/main/AGENTS.md).
