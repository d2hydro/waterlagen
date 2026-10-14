---
editorial_status: ai
---

# Aan de slag met Python

Stel een eigen workflow samen met de publieke Python-functies: bronnen ophalen,
een selectie maken, bewerken en het resultaat verder gebruiken of opslaan.
De voorbeelden tonen de afzonderlijke stappen en instelbare parameters.
Voor een complete standaardproductie zijn er de
[productiecommando's](../produceren/cli.md).

## Losse bronnen en bewerkingen

- [Bronlagen downloaden](bronlagen-downloaden.md): één script per bronlaag.
- [Bewerkte lagen samenstellen](bewerkte-lagen-produceren.md): één workflow per laag.
- [API-referentie](api.md): functies, parameters en teruggegeven resultaten,
  opgebouwd uit de actuele modulecode.

## Voorbereiden

Gebruik een geïnstalleerde [productieomgeving](../produceren/installatie.md)
of de [ontwikkelomgeving](../bijdragen/ontwikkelomgeving.md).
Download het gewenste `.py`-bestand vanaf de voorbeeldpagina en plaats het
in de map met `pixi.toml`. Pas bovenaan het script `DATA_DIR` aan naar de
gewenste gegevensmap. Alle voorbeelden gebruiken daar dezelfde submappen
`source_data` en `processed_data`, zodat bronnen kunnen worden hergebruikt.
Pas ook de gebiedskeuze, rekeninstellingen en experimentnaam aan. De invoer
en tussenresultaten staan expliciet in het script: vervang bijvoorbeeld een
downloadaanroep door een pad naar een eigen bestand met hetzelfde schema.

De voorbeelden horen bij de moduleversie waarmee deze documentatie is gebouwd.
Gebruik bij een oudere release de bijbehorende voorbeelden of werk de installatie bij.

## Een script uitvoeren

Begin bijvoorbeeld met het BGT-voorbeeld. Dat vraagt alleen waterdelen en panden
voor het voorbeeldgebied op:

```console
pixi run python download_bgt.py
```

Een bewerkte laag maakt u bijvoorbeeld met:

```console
pixi run python produceer_autos.py
```

Vanuit een repositorycheckout staan de scripts onder `docs/reference/voorbeelden/`:

```console
pixi run python docs/reference/voorbeelden/download_bgt.py
pixi run python docs/reference/voorbeelden/produceer_autos.py
```

Afwateringseenheden vereist PCRaster. Gebruik daarvoor vanuit de repository:

```console
pixi run --environment afwateringseenheden python docs/reference/voorbeelden/produceer_afwateringseenheden.py
```

In het productiepakket is PCRaster onderdeel van de productieomgeving; gebruik
daar `pixi run --locked python produceer_afwateringseenheden.py`.

## Het voorbeeldgebied

Waar een gebiedsselectie mogelijk is, gebruiken alle scripts **Alkmaar-centrum**
(`alkmaar_centrum`). Dat is een selectie van 1 × 1 km. Het landgebruikvoorbeeld
berekent deze rechthoek; het DEM volgt dat raster. Afwateringseenheden gebruikt
een kerntegel van 1 km met buffer en knipt het samengevoegde resultaat op het
gebied. Inwoners en auto's behouden complete CBS-buurten met alle woon-VBO's.
Dit zijn eigen workflows; de [standaardproductie](../produceren/cli.md#gebieden)
gebruikt grotere tegels en behoudt de volledige tegelkernen.

Een klein voorbeeldgebied betekent niet dat alle voorbeelden snel klaar zijn.
BAG, TOP10NL en andere bronnen worden landelijk gedownload. Ook de voorbereiding
van BAG/CBS is landelijk. Op iedere voorbeeldpagina staat welke gegevens nodig
zijn; de volledige productie kan veel schijfruimte, geheugen en tijd vragen.

## In eigen code gebruiken

Importeer de benodigde functies uit `waterlagen`. De scripts bevatten geen
extra `main()`-functie. Instellingen staan bovenaan, gevolgd door de stappen
binnen `if __name__ == "__main__":`. Dat blok voorkomt dat importeren de
workflow start en maakt multiprocessing veilig, ook op Windows.

In een notebook kunt u de imports, instellingen en stappen als losse cellen
gebruiken. Laat daarbij de buitenste `__main__`-voorwaarde en de bijbehorende
inspringing weg. Begin met één werkproces; start parallelle workflows vanuit
het script. Bekijk tussenresultaten voordat u ze aan de volgende functie doorgeeft.

`production_logging()` toont de voortgang en herstelt na afloop de eerdere
loggingconfiguratie. De voorbeelden hergebruiken bronbestanden en schrijven
naar `data/processed_data/voorbeelden/alkmaar_centrum/<experiment>/`.
Kies een nieuwe experimentnaam bij gewijzigde invoer of rekeninstellingen:
de losse functies bieden niet dezelfde bewaking van wijzigingen als de
[productie-API](productie.md). Een bestaand bestand kan worden hergebruikt
zonder dat gewijzigde parameters opnieuw worden toegepast.

## Verdelingen controleren

Voor het controleren van resultaten zijn ook
`waterlagen.vbo_buurt.statistiek.lees_verdelingstatistieken` en de
[BAG-controlefuncties](functioneel_landgebruik.md) beschikbaar.
Vergelijk regionale verdelingen alleen met de bijbehorende CBS-buurten:
de standaardstatistiek leest landelijke CBS-totalen.
