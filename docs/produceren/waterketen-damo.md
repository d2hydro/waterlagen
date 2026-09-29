# Waterketen DAMO downloaden

Volg eerst de [installatie-instructies](installatie.md). De betekenis en
beperkingen van de gegevens staan bij [Waterketen DAMO](../bronnen/waterketen-damo.md).

Gebruik in Python:

```python
from waterlagen.waterketen_damo import download_waterketen_damo

resultaat = download_waterketen_damo(overwrite=False)
print(resultaat.target_path)
```

De standaardlocatie is
`datastore.waterketen_damo_dir / "waterketen_damo.gpkg"`, oftewel
`source_data/waterketen_damo/waterketen_damo.gpkg` onder de ingestelde gegevensmap.
Zie [Opslag van gegevens](configuratie.md) voor de configuratie.
Met `download_dir` kiest u een andere map; `target_path` overschrijft het volledige
uitvoerpad. Beide accepteren een `pathlib.Path`.

Met `overwrite=False` wordt een bestaand bestand zonder download of hervalidatie
hergebruikt. Gebruik `overwrite=True` (de standaard) om de actuele bron opnieuw
op te halen. Nieuwe downloads worden gevalideerd en zo nodig naar `settings.crs`
omgezet voordat ze het doelbestand atomair vervangen. Een mislukte download laat
een bestaand doelbestand intact. Er wordt geen ruimtelijke selectie uitgevoerd.

`progress=False` schakelt de downloadvoortgang uit; `timeout` bepaalt de
HTTP-time-out in seconden. Zie ook de [API-referentie](../reference/waterketen_damo.md).
