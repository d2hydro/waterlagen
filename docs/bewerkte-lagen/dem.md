---
editorial_status: human
---

# Digitaal Hoogtemodel

## Doel

Deze bewerking combineert het AHN-terreinmodel (DTM) met één afgeleide hoogte per
individueel gebouw. De gebouwcellen zijn gedefinieerd in het bronnenraster van
[functioneel landgebruik](functioneel-landgebruik.md).

## Bronlagen

- [AHN-DTM](../bronlagen/ahn.md), inclusief omliggende rastertegels.
- De landgebruiktegels met `bronnen`, `gebouw_ids` en volledige voorbereide
  gebouwgeometrieën. De oorspronkelijke [BAG-identificatie](../bronlagen/bag.md)
  blijft in deze afgeleide gebouwgegevens bewaard. De DEM-bewerking selecteert
  zelf geen BAG-panden.

## Werkwijze

Waterlagen verdeelt het gekozen gebied, bijvoorbeeld een waterschap of heel Nederland, in vierkante tegels. Elke tegel krijgt een buffer rondom, zodat de berekeningen ook rekening houden met de omgeving. Per tegel wordt het AHN geïnterpoleerd en worden pandhoogtes toegevoegd.

De resultaten worden samengevoegd tot één hoogtemodel. Een VRT-bestand verbindt de tegels tot een mozaïek. Dit wordt opgeslagen in twee Cloud Optimized GeoTIFF-bestanden (COG): één met gehele getallen en een schaalfactor, en één met kommagetallen (floats).

### AHN interpoleren

Ontbrekende AHN-hoogtes worden geschat op basis van omliggende, oorspronkelijke AHN-hoogtes met inverse-distance-weighting. De maximale zoekafstand is instelbaar en bedraagt standaard 250 meter. Zonder bruikbare hoogtes binnen die afstand blijft een gat open. Eerder geschatte hoogtes worden niet gebruikt om andere gaten te vullen.

Bestaande AHN-hoogtes blijven behouden. Het aanvullen gebeurt los van de berekening van gebouwhoogtes en kan ook buiten het landgebied plaatsvinden. Daarna krijgen de gebouwhoogtes voorrang op de plekken die als gebouw zijn aangemerkt.
AHN-tegels kunnen ook afzonderlijk worden aangevuld en opgeslagen, zonder de rest van het hoogtemodel te produceren. Daarbij kan worden aangegeven waar gaten mogen worden gevuld. Dezelfde maximale zoekafstand blijft gelden.

### Pandhoogtes bepalen

Alleen rastercellen waarvoor BAG de bron is in het functionele landgebruik, tellen mee als gebouw. Aangrenzende panden blijven afzonderlijk herkenbaar, ook als hun gebruik onbekend is.

De gebouwhoogte wordt afgeleid uit de oorspronkelijke AHN-hoogtes rondom het volledige pand, ook als dat over een tegelgrens ligt. Hoogtes binnen het pand of buurpanden tellen niet mee. De zoekafstand begint bij 1 meter en wordt zo nodig in stappen van 1 meter vergroot tot maximaal 5 meter.

Zodra bruikbare hoogtes zijn gevonden, wordt het 75e percentiel als gebouwhoogte gebruikt: een hoogte waar ongeveer driekwart van de gevonden waarden op of onder ligt. Er wordt geen vaste vloerhoogtetoeslag bij opgeteld.

De hoogte, BAG-identificatie, zoekafstand en het aantal donors (gebruikte AHN-hoogtes) worden bewaard in `gebouwhoogten.gpkg`.

### Bronnen
Per cel wordt de bron van de hoogte-waarde bijgehouden op 2 nivo's:
- `ahn_bron` geeft per rastercel aan waar de terreinhoogte vandaan komt: oorspronkelijk AHN-DTM (1), inverse-distance-interpolatie (3) of ontbrekend (0).
- `dem_bron` geeft de herkomst van de hoogte in het uiteindelijke hoogtemodel. Daarin krijgen cellen met een geslaagde gebouwhoogte code 2. De overige cellen behouden de code uit ahn_bron.

###  Ontbrekende hoogtes (nodata)

Per tegel wordt vastgelegd waar geen hoogte kon worden bepaald. Deze plekken worden samengevoegd in `nodata.gpkg`, met drie categorieën:
- **AHN bij water**: ontbrekende terreinhoogtes die na het aanvullen overblijven op plekken die in het functionele landgebruik als water zijn ingedeeld.
- **AHN bij overig landgebruik**: dezelfde ontbrekende terreinhoogtes, maar buiten de als water ingedeelde plekken.
- **Gebouwen**: panden waarvoor binnen de maximale zoekafstand geen bruikbare AHN-hoogtes zijn gevonden om een gebouwhoogte te bepalen.

**Let op (!)**: Een melding betekent niet altijd dat het uiteindelijke hoogtemodel daar leeg is. Een ontbrekende AHN terreinhoogte kan alsnog worden bedekt door een gebouwhoogte. En ook; waar geen pandhoogte bepaald kan worden kunnen deze cellen alsnog opgevuld zijn door terrein-interpolatie.

### Samenvoegen tegels
De berekende tegels worden met een [VRT-bestand](https://gdal.org/en/stable/drivers/raster/vrt.html) samengebracht tot één tegel mozaïek. Het VRT verwijst naar de rasters in de verschillende tegels. Dit mozaïek wordt vervolgens opnieuw opgeslagen als één Cloud Optimized GeoTIFF (COG), met gehele getallen en een schaalfactor (scale) van 0.01 voor de hoogte. De toepassing van scale wordt ondersteund door GDAL en daarmee doorgaans ook door software die GDAL gebruikt, zoals QGIS en Rasterio (Python). Of de schaalfactor automatisch wordt toegepast bij het uitlezen of verwerken van rasterwaarden, verschilt per toepassing.

Daaruit wordt een tweede COG gemaakt waarin de hoogtes direct in meters als kommagetallen (floats) zijn opgeslagen. Beide bestanden bevatten dezelfde hoogtes; de floatversie voegt geen nauwkeurigheid toe.

## Uitvoer
Een volledige productie bevat:

- dem.vrt en dem.tif (COG): hoogtemodel, bij standaardinvoer als Int16 in cm NAP met schaalfactor 0,01 naar m NAP.
- dem_float.tif (COG): dezelfde hoogtes als Float32 in m NAP, met schaalfactor 1.
- dem_bron en ahn_bron, beide als VRT en COG: herkomst van de hoogtes, respectievelijk na en vóór toevoeging van gebouwhoogtes. Codes: 0 = ontbrekend, 1 = origineel AHN, 2 = gebouwhoogte (alleen dem_bron), 3 = interpolatie.
- nodata.gpkg, laag nodata: ontbrekende gebouwhoogtes en resterende AHN-gaten.
- gebouwhoogten.gpkg: berekende hoogtes per gebouw.
- tiles.gpkg: tegelkernen van het productiegebied.
Per tegel staan in tiles/<xmin_ymin_xmax_ymax>/ de rasters ahn_aangevuld.tif, ahn_bron.tif, gebouwhoogten.tif en dem_bron.tif, plus nodata.gpkg, status.json en workflow.log.

nodata.gpkg vermeldt per plek de bron, categorie en reden waarom een hoogte ontbreekt. Bij gebouwen worden ook de BAG-identificatie, zoekafstand en het aantal gebruikte AHN-cellen vastgelegd. Gebouwen staan eenmaal met hun volledige vorm in het bestand; AHN-gaten volgen de rastercellen.

dem_coverage.json bevat de aantallen resterende lege cellen na het combineren van terrein- en gebouwhoogtes, uitgesplitst naar buiten het landgebied, water binnen het landgebied en overig landgebied. Ook als er gaten overblijven, worden de uitvoerbestanden aangemaakt.

## Aandachtspunten en beperkingen
De aandachtspunten die volgen uit de beschrijving hierboven:
- Gebouwhoogtes zijn geschat uit het omliggende terrein, niet gemeten aan het gebouw. Elk pand krijgt één hoogte; verschillen binnen het pand worden niet weergegeven.
- Geïnterpoleerde hoogtes zijn schattingen. Lokale hoogteverschillen die niet in de omliggende AHN-cellen voorkomen, kunnen daarmee niet worden hersteld.
- Gaten kunnen blijven bestaan door de beperkte zoekafstand. Als een gebouwhoogte ontbreekt, kan daar nog wel een terreinhoogte staan. Bekijk daarom nodata.gpkg, ahn_bron en dem_bron.
- De standaarduitvoer slaat hoogtes op in stappen van één centimeter. Dit zegt niets over de meetnauwkeurigheid; omzetting naar floats maakt de hoogtes niet nauwkeuriger.
- Gebouwen in nodata.gpkg worden volledig weergegeven en kunnen buiten het uitvoergebied uitsteken. Bewaar de tegelbestanden zolang het VRT nodig is.

**Het belangrijkste**: Bekijk altijd `nodata.gpkg`, `ahn_bron` en `dem_bron` om hoogtes te verklaren.

## Zelf produceren

Begin met [DEM-productie voor Nederland of Alkmaar](../produceren/dem.md).
De Python-interface staat bij [DEM-API](../reference/dem.md).
