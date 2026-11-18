---
editorial_status: ai
---

# Gegevensmappen opvragen

??? info "Gegevensmappen opvragen · `DataStore`"

    `DataStore()` leest de ingestelde [opslaglocaties](../produceren/configuratie.md#gegevens-ergens-anders-bewaren).

    **Wat krijgt u terug?** Een `DataStore`. Gebruik `source_data_dir` voor bronbestanden en `processed_data_dir` voor resultaten.

    **Instellingen en invoer**

    | Naam | Type | Betekenis | Standaardwaarde |
    | --- | --- | --- | --- |
    | `data_dir` | `Path` | Basismap voor gegevens. | De ingestelde gegevensmap. |
    | `source_data_dir` | `Path` | Map voor bronbestanden. | `data_dir / "source_data"` tenzij apart ingesteld. |
    | `processed_data_dir` | `Path` | Map voor resultaten. | `data_dir / "processed_data"` tenzij apart ingesteld. |

    ```python
    from waterlagen.datastore import DataStore

    store = DataStore()
    print(store.source_data_dir)
    ```
