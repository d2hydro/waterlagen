# Functioneel landgebruik

## Doel

Deze bewerking maakt een geclassificeerd raster voor functioneel landgebruik.

## Bronnen

- [TOP10NL](../bronnen/top10nl.md)
- [BRP](../bronnen/brp.md)
- [BGT](../bronnen/bgt.md)
- [BAG](../bronnen/bag.md)
- [Dijkringen](../bronnen/dijkringen.md)

## Werkwijze

Waterlagen leest de benodigde vectorlagen binnen het gevraagde gebied,
classificeert bronattributen naar de functionele-landgebruiklegenda en
rasteriseert de lagen in een vaste prioriteitsvolgorde. TOP10NL, BRP, BGT-wegen
en BAG-klassen worden onderscheiden naar binnen- en buitendijks op basis van
hun representatieve punt en de dijkringgeometrie.

## Uitvoer

De uitvoer is een gepaletteerde GeoTIFF met één `uint8`-band `Landgebruik`,
NoData-waarde 0 en overviews. De standaardresolutie is 0,5 m en de standaard-CRS
is `EPSG:28992`.

## Aandachtspunten en beperkingen

De classificatie volgt de in Waterlagen vastgelegde legenda en de beschikbare
bronattributen. Het raster is daarom een afgeleid product, geen vervanging van
een afzonderlijke bronregistratie. Ontbrekende bronbestanden kunnen desgewenst
vooraf door de workflow worden gedownload.

## Zelf produceren

Gebruik `bouw_functioneel_landgebruik` of de workflow in `scripts/`; zie de
[API-referentie](../reference/functioneel_landgebruik.md).
