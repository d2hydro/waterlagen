# Functioneel landgebruik produceren

Het productiepakket bevat `scripts/functioneel_landgebruik.py` voor het maken
van een landelijk raster met functionele landgebruiksklassen. De betekenis van
de klassen, bronnen en bewerkingen staat bij
[Functioneel landgebruik](../bewerkingen/functioneel-landgebruik.md).

## Vooraf

Volg [Installatie](installatie.md) en controleer het productiepakket met
`pixi run --locked controleer`. Gegevens komen standaard onder `./data` in de
projectfolder; zie [Opslag van gegevens](configuratie.md) voor een andere locatie.

Dit voorbeeld verwerkt een landelijk tegelrooster. Downloads en berekeningen
kunnen veel schijfruimte en tijd vragen. Controleer de instellingen in het
script en de functionele beschrijving voordat u de productie start.

## Starten

Open [PowerShell in uw projectfolder](installatie.md#powershell-openen-in-uw-projectfolder)
en voer uit:

```powershell
pixi run --locked landgebruik
```

De taak voert het meegeleverde script uit. Rechtstreeks starten kan ook:

```powershell
pixi run --locked python ./scripts/functioneel_landgebruik.py
```

Het script maakt tegels van 5 × 5 km en verwerkt maximaal drie tegels tegelijk,
afhankelijk van het aantal beschikbare processorkernen. Het hergebruikt bestaande
uitvoer waar de onderliggende bewerkingen dat ondersteunen. Voor een aangepaste
productie kunt u de instellingen en aanroepen in uw kopie van het script wijzigen.

## Resultaten

Onder `data/processed_data/functioneel_landgebruik` vindt u:

- `tiles/`: de berekende rastertegels;
- `functioneel_landgebruik.vrt`: de tegels samengevoegd als virtueel raster;
- `functioneel_landgebruik.tif`: het samengestelde Cloud Optimized GeoTIFF-raster.

Het logbestand is `data/bouw_functioneel_landgebruik.log`. Open het resultaat
in QGIS en controleer de dekking en klassen voor uw toepassing.
