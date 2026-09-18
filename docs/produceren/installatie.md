# Installatie

Met Conda installeert u Waterlagen samen met Python en de benodigde GIS-software.
U hoeft daarvoor geen Python-code te schrijven. De onderstaande route gebruikt
de commandline-interface van versie **2026.2.2**.

!!! warning "Publicatie in voorbereiding"
    Versie 2026.2.2 is nog niet gepubliceerd op conda-forge. Gebruik voorlopig
    het [lokaal gebouwde pakket](#lokaal-gebouwd-pakket) of de
    [ontwikkelomgeving](#vanuit-de-broncode). Versie 2026.2.1 heeft deze
    commandline-interface nog niet.

## 1. Installeer Miniforge

Download [Miniforge](https://conda-forge.org/download/) voor uw besturingssysteem
en voer de installer uit. Open op Windows daarna **Miniforge Prompt** vanuit het
Startmenu. Voer de volgende opdrachten in die prompt uit.

## 2. Installeer Waterlagen

Na publicatie op conda-forge:

```console
conda create --name waterlagen --override-channels --channel conda-forge waterlagen=2026.2.2 pcraster
conda activate waterlagen
```

Bevestig de installatie wanneer Conda daarom vraagt. Conda kiest een passende
Python-versie (minimaal 3.11) en installeert onder andere GDAL. PCRaster is nodig
voor afwateringseenheden; voor andere Python-workflows is het optioneel.

### Lokaal gebouwd pakket

Zolang conda-forge-publicatie nog ontbreekt, kan de beheerder een lokaal
conda-kanaal aanleveren volgens de [bouwinstructies](../bijdragen/conda-forge.md).
Plaats de aangeleverde kanaalmap bijvoorbeeld in `D:/Waterlagen/conda-packages`.
Daarin moet de submap `noarch` staan, met het pakket en `repodata.json`.

Gebruik dan deze opdrachten in plaats van de opdrachten hierboven:

```console
conda create --name waterlagen --override-channels --channel D:/Waterlagen/conda-packages --channel conda-forge waterlagen=2026.2.2 pcraster
conda activate waterlagen
```

Vervang de kanaalmap door de werkelijk ontvangen locatie. Internet blijft nodig
voor de overige pakketten uit conda-forge.

## 3. Controleer de installatie

Kies een schrijfbare map voor uw gegevens. In de voorbeelden is dat
`D:/Waterlagen/data`; vervang die locatie zo nodig. Zet paden met spaties tussen
dubbele aanhalingstekens.

```console
waterlagen --version
waterlagen controleer --data-dir D:/Waterlagen/data
```

De controle voert een kleine rasterberekening uit en test de opslag. Er worden
geen brongegevens gedownload. Bij succes verschijnt **Installatie OK**.
Ga daarna verder met [Afwateringseenheden produceren](afwateringseenheden.md).

Open bij een volgende sessie opnieuw Miniforge Prompt en voer eerst
`conda activate waterlagen` uit. Met `waterlagen --help` ziet u de opdrachten.

## Vanuit de broncode

Ontwikkelaars gebruiken [de Pixi-ontwikkelomgeving](../bijdragen/ontwikkelomgeving.md).
Vanuit de repository-root zijn dezelfde opdrachten beschikbaar:

```console
pixi run --environment afwateringseenheden waterlagen --help
pixi run --environment afwateringseenheden waterlagen controleer --data-dir D:/Waterlagen/data
```

De geïnstalleerde pakketversie volgt hier de Git-versie van de checkout.

## Bestaande Python-omgeving

De [Python-voorbeelden](eerste-dataset.md) blijven beschikbaar. Installatie met
`pip install waterlagen` vereist een omgeving waarin ook de native
GIS-bibliotheken correct zijn geïnstalleerd. Een fout zoals
`Cannot open include file: 'gdal.h'` betekent dat pip GDAL probeert te compileren
zonder de benodigde ontwikkelbestanden. Gebruik voor de installatie hierboven
Conda: daarmee worden de voorgebouwde bibliotheken meegeleverd.
