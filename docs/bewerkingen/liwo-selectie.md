# LIWO-selectie van overstromingsgevoelige gebieden

## Doel

Maak polygonen van buitendijks en regionaal onbeschermd overstroombaar gebied.

## Bronnen

- [LIWO overstromingsgevoelige gebieden](../bronnen/liwo.md)

## Werkwijze

Het oorspronkelijke klassenraster wordt zonder herschaling of herprojectie
gedownload. Alleen geldige cellen met waarde 1 of 6 worden gepolygoniseerd.
NoData en alle overige waarden worden uitgesloten. Cellen met dezelfde klasse
worden verbonden langs gedeelde zijden; alleen diagonaal rakende cellen blijven
afzonderlijke polygonen. De twee klassen blijven gescheiden.

## Parameters en aannames

De verwerking behoudt EPSG:28992 en het 25 m bronraster. Een gewijzigde nationale
dekking, resolutie, gegevenstype of onverwachte klassewaarde geeft een foutmelding
zodat de servicemetadata eerst opnieuw kan worden gecontroleerd.

## Resultaat

Een GeoPackage met laag `overstromingsgevoelige_gebieden_selectie` en attributen
`klasse` en `omschrijving`. Het volledige gedownloade GeoTIFF blijft als bron bewaard.
Bij een lege selectie bevat de uitvoer een lege polygonenlaag.

## Beperkingen

Polygonen volgen exact de rastercellen; er wordt niet vereenvoudigd of gladgestreken.
Deze selectie vervangt niet automatisch de dijkringenbron in andere workflows.

## Zelf produceren

Zie [het scriptvoorbeeld](../produceren/voorbeelden.md#liwo-gebieden-downloaden-en-polygoniseren).
