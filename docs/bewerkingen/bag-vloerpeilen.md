# BAG-vloerpeilen

## Doel

Deze bewerking maakt een raster met vloerpeilen voor BAG-panden op basis van
een digitaal hoogtemodel.

## Bronnen

- [BAG](../bronnen/bag.md)
- [AHN](../bronnen/ahn.md) of een ander aangeleverd DEM-raster

## Werkwijze

Voor elk pand wordt uit het DEM een vloerpeil afgeleid. Waterlagen rasteriseert
de pandgeometrie met die waarde naar het grid van het aangeleverde DEM-raster.
Een bufferstap bepaalt hoe de pandgeometrie bij de bepaling wordt behandeld.

## Uitvoer

De uitvoer is één GeoTIFF. De cellen binnen panden bevatten het afgeleide
vloerpeil; de gridindeling volgt het DEM. In de gebruikte BAG-GeoDataFrame
wordt de berekende waarde als `vloerpeil` vastgelegd.

## Aandachtspunten en beperkingen

Het resultaat hangt af van de kwaliteit, dekking en resolutie van het DEM en
van de geselecteerde BAG-panden. Het is geen zelfstandig brongegeven uit de BAG.

## Zelf produceren

Haal panden en een DEM op, en gebruik `rasterize_bag`; zie de
[BAG-API](../reference/bag.md).
