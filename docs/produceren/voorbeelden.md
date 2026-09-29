# Voorbeelden

Het [productiepakket](installatie.md) bevat de scripts voor
[afwateringseenheden](afwateringseenheden.md), [landgebruik](landgebruik.md) en
[inwoners en personenauto's](inwoners-personenautos.md), plus BAG-light als
voorbereiding en een script voor controle van de inwoners- en autototalen.

De bestanden onder `scripts/` in het pakket zijn dezelfde openbare voorbeelden
als in de repository bij die release. Pas de instellingen aan uw toepassing aan.
Gebruik steeds de scripts en het Pixi-lockbestand uit hetzelfde pakket.

De broncoderepository bevat aanvullende workflows voor onder meer BGT, BRP,
TOP10NL, LIWO en HYDAMO. Deze zitten niet allemaal in het productiepakket.
Gebruik daarvoor de [ontwikkelomgeving](../bijdragen/ontwikkelomgeving.md).

## LIWO-gebieden downloaden en polygoniseren

Voer vanuit de broncoderepository uit:

```powershell
pixi run python scripts/liwo_overstromingsgevoelige_gebieden.py
```

Het script downloadt het nationale GeoTIFF naar `source_data/liwo/` en schrijft
`source_data/liwo/buitendijks_gebied_uit_liwo.gpkg`, onder de
geconfigureerde [DataStore](configuratie.md). De geselecteerde klassen en methode
staan bij [LIWO-selectie](../bewerkingen/liwo-selectie.md).

Een bestaand raster wordt gevalideerd en hergebruikt; met `--overwrite` wordt
het opnieuw gedownload. De polygonen worden bij iedere uitvoering opnieuw gemaakt.
Beide doelbestanden worden pas vervangen na succesvolle validatie. Gebruik
`--raster` en `--output` voor andere uitvoerpaden, `--timeout` voor de HTTP-time-out
(standaard 300 seconden) en `--no-progress` om downloadvoortgang te verbergen.
