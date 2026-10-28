---
editorial_status: ai
---

# Afwateringseenheden produceren

Deze productie ondersteunt Nederland, een waterschapscode en gedeelde gebieden
zoals Alkmaar. Volg eerst [Installatie](installatie.md).

## Starten

Open een terminal in de map waarin `pixi.toml` staat.
Kies een van de volgende opdrachten:

```console
pixi run --locked afwateringseenheden --area alkmaar --workers 2
pixi run --locked afwateringseenheden --waterbeheercode 38 --workers 2
```

Gebruikt u de broncode uit GitHub? Voeg dan `--environment afwateringseenheden`
toe na `pixi run`.

Zonder `--area`, `--waterbeheercode` of `--bounds` wordt **heel Nederland** verwerkt.
Een onbekende waterschapscode geeft een fout voordat AHN en HYDAMO worden opgehaald.

Zie [meer commandline-opties](cli.md) voor meer uitleg en aanvullende instellingen.

## Workflow

### Eigen gebied met brandlagen

1. Zet de gewenste bestanden en lagen in de [brandlagen-TOML](#toml-configuratie).
   Sla deze voor dit voorbeeld op als `invoer/brandlagen.toml`.
2. Start de productie met uw brandlagenconfiguratie:

   ```console
   pixi run --locked afwateringseenheden --bounds 184285 392054 185285 393054 --brandlagen-config ./invoer/brandlagen.toml
   ```

3. Open `afwateringseenheden.gpkg` uit de resultaatmap in QGIS.

Het voorbeeld verwerkt de volledige rekentegel van 10 × 10 km waarin het opgegeven gebied ligt.

## Doelmodi en bronnen

| Optie | Gebruik |
| --- | --- |
| `--overige-waterschappen` | Neem bij een waterschapselectie ook afwateringsdoelen van andere waterschappen mee. |
| `--eigen-hydamo eigen.gpkg` | Vervang de GKW-gegevens van het gekozen waterschap door een eigen HYDAMO-GeoPackage. |
| `--rijkswateren-url` | Stel een andere locatie voor de Rijkswaterenbron in. |

Zie [afwateringsdoelen](../bewerkte-lagen/afwateringseenheden.md#afwateringsdoelen)
voor het effect van de gebiedsselectie.

```console
pixi run --environment afwateringseenheden afwateringseenheden --waterbeheercode 38 --overige-waterschappen
pixi run --environment afwateringseenheden afwateringseenheden --waterbeheercode 38 --eigen-hydamo eigen.gpkg
```

### Eigen levering

`--eigen-hydamo` vervangt de GKW-gegevens van het gekozen waterschap.
GKW blijft beschikbaar voor de omgeving.

- Verplicht: `hydroobject`, `gemaal`, `stuw` en `duikersifonhevel`.
- Kunstwerklagen mogen leeg zijn. Ontbrekende gegevens worden niet uit GKW aangevuld.
- Elk object moet een geldig `nen3610id` van het gekozen waterschap hebben.
- Het coördinatenstelsel (CRS) en de waterloopcategorie moeten bekend zijn.

De categorie staat in `categorieoppwaterlichaam` of `categorieoppervlaktewater`.
`primair`, `secundair` en `tertiair` doen mee; `overig` niet.
GKW-waterlopen zonder categorie komen in `controle.gpkg`.

## Duikers, sifons en hevels

- HYDAMO-duikers worden gelezen uit `duikersifonhevel`.
- RWS-duikers komen alleen uit de optionele duikerlaag in de Rijkswaterenbron.
- BGT- en OSM-duikers worden toegevoegd via de [TOML](#toml-configuratie).

Bij de koppeling aan primaire waterlopen is de koppelafstand standaard **0,5 m**
per uiteinde. Aanpassen kan met `--duiker-tolerance`.
Zie de [koppelregels](../reference/afwateringseenheden.md#duikervoorbereiding).

Met `--max-aansluitlengte 50` worden ook direct aansluitende stukken van maximaal
50 m uitgesloten als afwateringsdoel. Ze blijven wel ingebrand.
Zonder deze optie blijven aansluitstukken afwateringsdoelen.

Zie [waterlopen en duikers inbranden](../bewerkte-lagen/afwateringseenheden.md#waterlopen-en-duikers-inbranden)
voor de verwerking.

### Controle in QGIS

Open `controle.gpkg` naast `watersysteem.gpkg`.

| Controlelaag | Wat controleren? |
| --- | --- |
| `duikersifonhevel` | Koppeling aan primaire waterlopen; zie `reden`, `afstand_begin` en `afstand_eind`. |
| `duikers_waternet` | Behandeling op het raster; zie `behandeling` en `reden`. |

Een duiker zonder primaire koppeling kan wel bij een secundaire waterloop horen.
Gebruik `bronbestand`, `bronlaag` en `bron_fid` om het oorspronkelijke object terug te vinden.

Zie de [betekenis van de velden](../bewerkte-lagen/afwateringseenheden.md#uitvoer)
voor `brandgeschikt` en `doelgeschikt`.

### Afwateringseenheid aan een segment koppelen

Gebruik `segment_id` uit de afwateringseenheid om hetzelfde segment in
`hydroobject_segment` te vinden. `van_segment` en `naar_segment` in
`hydroobject_verbinding` gebruiken deze nummers ook.

Gebruik bestanden uit dezelfde run. Broninformatie staat in `hydroobject_segment`.

## Optionele brandlagen

Voeg lijnen en vlakken uit GeoPackages toe via de [TOML](#toml-configuratie).
De [functionele handleiding](../bewerkte-lagen/afwateringseenheden.md#optionele-brandlagen)
beschrijft hun werking en de regels bij overlap.

| Instelling | Betekenis |
| --- | --- |
| `brandwaarde` | Hoogtewijziging in meters: negatief verlaagt, positief verhoogt. |
| `prioriteit` | Hoger getal heeft voorrang bij overlap tussen aanvullende lagen. |

- Een waarde bij het object gaat voor de TOML-instelling van de laag, daarna geldt `[defaults]`.
- Gebruik een vlak als u een lijn met een bepaalde breedte wilt inbranden.

### Waterlopen en duikers

De [regels voor inbranding en duikers](../bewerkte-lagen/afwateringseenheden.md#waterlopen-en-duikers-inbranden)
staan in de functionele handleiding.

- `geisoleerde_branddiepte_m`: vervangt de standaardverlaging van 10 m voor HYDAMO-waterlopen en -duikers in de [tabel](../bewerkte-lagen/afwateringseenheden.md#waterlopen-en-duikers-inbranden).

### TOML-configuratie

[Download de voorbeeld-TOML](../reference/voorbeelden/brandlagen.toml).
Plaats deze naast `source_data` of pas de paden aan.

| Onderdeel | Invullen |
| --- | --- |
| `path`, `layer` | Bestand en laagnaam. Relatieve paden gelden vanaf de TOML. |
| `brandwaarde`, `prioriteit` | Waarden voor de laag; mogen ook per object zijn ingevuld. |
| `rol` | `water`, `duiker` of `overig` (bijvoorbeeld wegen). |
| `bron` | Bij duikers verplicht: `hydamo`, `bgt` of `osm`. |
| `[defaults]` | Standaardwaarden voor alle lagen. |

De bronnen moeten vooraf beschikbaar zijn:

- BGT en TOP10NL: bestaande GeoPackages.
- BGT-duikers: selectie van `bgt_kunstwerkdeel` met `plus-type = duiker`.
- OSM: het [downloadscript](../reference/bronlagen-downloaden.md#osm-kanalen) maakt vijf bestanden onder `source_data/osm/`.

Neem bij gebiedsselecties ook de tegelbuffers mee. De TOML downloadt niets.

In het voorbeeld geldt deze volgorde, met de hoogste prioriteit bovenaan:

| Aanvullende laag | Hoogtewijziging | Prioriteit |
| --- | ---: | ---: |
| BGT-water en BGT-duikers | -10 m | 2 |
| OSM-duikers | -10 m | 1 |
| OSM-kanalen, sloten, afvoerwatergangen en beken | -5 m | 1 |
| TOP10NL-waterdelen en waterlijnen | -5 m | 0 |

BGT-wegen staan uitgecommentarieerd: de proefwaarde is **+2 m**.

```toml
--8<-- "docs/reference/voorbeelden/brandlagen.toml"
```

```console
pixi run --environment afwateringseenheden afwateringseenheden --bounds 184285 392054 185285 393054 --brandlagen-config brandlagen.toml --workers 32
```

### Brandlagen controleren in QGIS

| Bestand | Wat ziet u? |
| --- | --- |
| `brandlagen.gpkg` | Alle geselecteerde invoer, per bron in een aparte laag. |
| `berekening/tegels/<tegel>/brandbron.tif` | De gebruikte bron per rastercel. |

Niet elk object uit `brandlagen.gpkg` wordt ingebrand: overlap en duikerregels
bepalen wat wordt gebruikt. Bekijk daarvoor `brandbron.tif` en controleer
daarna de stroomrichtingen (LDD) en afwateringsvlakken.

Broncodes zijn labels, geen prioriteiten. `0` betekent geen inbranding.
De legenda staat bij `broncodes` in de rastermetadata.

## Uitvoer en hervatten

Elke run staat onder `processed_data/afwateringseenheden/<gebied>/<run-id>/`.

| Bestand | Inhoud |
| --- | --- |
| `afwateringseenheden.gpkg` | Het eindresultaat, met één laag: `afvoergebiedaanvoergebied`. |
| `brandlagen.gpkg` | Alle geselecteerde brandinvoer, met afzonderlijke lagen per bron. |
| `watersysteem.gpkg` | Vijf lagen: primaire, secundaire en niet-verbonden secundaire waterlopen, segmenten en verbindingen. |
| `controle.gpkg` | Niet-toegewezen gebieden, aanvullingen uit buurtegels, duikercontroles en bronobjecten zonder categorie. |
| `berekening/` | Tussenbestanden voor de berekening en het hervatten. |
| `productie.log` | Hoofdlog, inclusief de werkprocessen. |
| `run.json` | Instellingen, bronidentiteit, pakketversie en runstatus. |

Lever voor normaal gebruik `afwateringseenheden.gpkg` en `watersysteem.gpkg`.
Geef `controle.gpkg` apart mee voor beoordeling.
`brandlagen.gpkg` helpt bij het bekijken van de gebruikte invoer.

Onder `berekening/` staan:

- `ahn/`: verwijzingen naar de gebruikte AHN-tegels.
- `watersysteem/`: tussenlagen van de primaire waterlopen.
- `waterlopen_duikers/`: rasters met de gekozen behandeling van waterlopen en duikers.
- `tegels/`: resultaten per tegel en de tegelindeling in `tiles.gpkg`.
  `brandlagen_voorbereid.gpkg` bevat hier de aanvullende brandlagen voor het rekenen.

Gebruik voor het bekijken van de invoer **`brandlagen.gpkg` in de hoofdmap**.
Bewaar `berekening/` als u de run wilt hervatten.
Ook bij overgeslagen tegels blijven de voorbereide rasters hier beschikbaar.
De nieuwe indeling geldt voor nieuwe runs. Begin voor uitvoer met de oude
mapindeling een nieuwe run; bestaande bestanden worden niet verplaatst.

Niet-toegewezen gebieden staan in `controle.gpkg`, laag `niet_toegewezen`.
Controleer daar op ontbrekende bronnen, tegelranden en rekenproblemen.

```console
pixi run --locked afwateringseenheden --area alkmaar --run-id proef
pixi run --locked afwateringseenheden --area alkmaar --run-id proef --resume
```

Fouten in afzonderlijke tegels verhinderen het samenvoegen, terwijl overige
onafhankelijke tegels worden afgewerkt. Hervatten hergebruikt geldige resultaten.
Zie [productiemappen](configuratie.md#productiemappen) voor de compatibiliteitsvoorwaarden.

Gebruik na wijzigingen aan bronnen of instellingen een nieuwe run-ID.
`--resume` is alleen bedoeld voor dezelfde invoer en instellingen.
Bewerk invoer niet tijdens een berekening.

Gebruik voor eigen code de [Python-ingang](../reference/gebruik.md) of de
[lagere API](../reference/afwateringseenheden.md#dekking-en-hergebruik).
