---
editorial_status: ai
---

# Parallel rekenen met afwateringseenheden

Wijzigt u de tegelberekening? Controleer of één en zes workers dezelfde rasters en polygonen opleveren, ook bij hergebruik. De samenvoegtests controleren hoe buurpolygonen gaten vullen. Beide tests gebruiken kleine lokale datasets.

```bash
pixi run --environment afwateringseenheden pytest tests/test_afwateringseenheden_workers.py tests/test_afwateringseenheden_merging.py
```

## Eerdere meting

Op 14 september 2026 zijn dezelfde twee tegels van 2 × 2 km doorgerekend, met een buffer van 2 km, een resolutie van 2 m en seed 12345 per tegel.

| Workers | Totale rekentijd | Piekgeheugen |
| ---: | ---: | ---: |
| 1 | 128,2 s | 1,01 GB |
| 2 | 83,2 s | 1,76 GB |

De rasters en segmentpolygonen waren gelijk. De meting met één worker draaide eerst, waardoor bestandscaches de tweede meting kunnen hebben versneld. Gebruik deze tijden alleen voor deze proef.
