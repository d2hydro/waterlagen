---
editorial_status: human
---

# Afwateringseenheden produceren

## Starten

Volg eerst [Installatie](installatie.md). Open daarna een terminal in de map
waarin `pixi.toml` staat. Start bijvoorbeeld een run voor Aa en Maas met de
standaardbronnen:

```console
pixi run --locked afwateringseenheden --waterbeheercode 38 --workers 8 --run-id test
```

Gebruikt u de broncode uit GitHub? Voeg dan bij de opdrachten op deze pagina
`--environment afwateringseenheden` toe na `pixi run`.

Ontbrekende standaardbronnen (AHN, HYDAMO, Rijkswateren en gebiedsgrenzen) worden
automatisch opgehaald en voorbereid. Bestaande bronnen worden hergebruikt;
met `--offline` moeten de benodigde bronnen al lokaal beschikbaar zijn.
Aanvullende BGT-, TOP10NL- en OSM-brandlagen worden alleen gebruikt als u ze
opneemt in een TOML; zie de [brandlagentest](#test-met-eigen-gebied-en-brandlagen).
Eigen lokale brandlagen en een eigen HYDAMO-levering levert u zelf aan.

Zie [gebieden](cli.md#gebieden) voor de beschikbare selecties en hun omvang.

<span id="uitvoer-en-hervatten"></span>
<span id="controle-in-qgis"></span>
<span id="brandlagen-controleren-in-qgis"></span>
<span id="afwateringseenheid-aan-een-segment-koppelen"></span>

## Resultaten bekijken en controleren

Bij standaardopslag staat de voorbeeldrun in
`data/processed_data/afwateringseenheden/waterschap_38/test/`.
Andere runs volgen de indeling
`data/processed_data/afwateringseenheden/<gebied>/<run-id>/`.

1. Controleer of de opdracht zonder fout is afgerond en `run.json` de status
   `complete` heeft. Lees bij fouten `productie.log`.
2. Open `afwateringseenheden.gpkg` en `watersysteem.gpkg` samen in QGIS.
3. Beoordeel in `controle.gpkg` de niet-toegewezen gebieden (`niet_toegewezen`)
   en duikermeldingen (`duikersifonhevel` en `duikers_waternet`).

| Bestand | Inhoud |
| --- | --- |
| `afwateringseenheden.gpkg` | Eindresultaat, laag `afvoergebiedaanvoergebied`. |
| `watersysteem.gpkg` | Waterlopen, segmenten en verbindingen. |
| `controle.gpkg` | Niet-toegewezen gebieden, aanvullingen uit buurtegels en bron- en duikercontroles. |
| `brandlagen.gpkg` | Geselecteerde brandinvoer, met afzonderlijke lagen per bron. |
| `productie.log` | Voortgang en meldingen van de berekening. |
| `run.json` | Instellingen, bronidentiteit, pakketversie en runstatus. |

Een niet-toegewezen gebied betekent niet automatisch een softwarefout: er kan
bijvoorbeeld geen route naar een afwateringsdoel zijn. Zie
[Tegels, buffers en samenvoegen](../bewerkte-lagen/afwateringseenheden.md#tegels-buffers-en-samenvoegen)
en [uitvoer en veldbetekenissen](../bewerkte-lagen/afwateringseenheden.md#uitvoer).

??? info "Verdiepende controle"

    Vergelijk `brandlagen.gpkg` met `berekening/tegels/<tegel>/brandbron.tif`.
    Het GeoPackage toont de geselecteerde invoer; het raster toont de
    daadwerkelijk gebruikte bron per cel. De legenda staat bij `broncodes`
    in de rastermetadata; `0` betekent geen inbranding.
    Beoordeel ook het stroomrichtingenraster (LDD) en de afwateringsvlakken.

    Controleer bij duikerkoppelingen `reden`, `afstand_begin` en `afstand_eind`
    in `duikersifonhevel`, en `behandeling` en `reden` in `duikers_waternet`.
    Een duiker zonder primaire koppeling kan wel bij een secundaire waterloop horen.
    Met `bronbestand`, `bronlaag` en `bron_fid` vindt u oorspronkelijke objecten
    terug. Zie de [duikervoorbereiding](../reference/afwateringseenheden.md#duikervoorbereiding)
    voor de technische koppelvoorwaarden.

Lever `afwateringseenheden.gpkg` en `watersysteem.gpkg` samen.
Geef `controle.gpkg` mee voor beoordeling en zo nodig `brandlagen.gpkg` voor
inzicht in de invoer. Houd bestanden uit dezelfde run bij elkaar.

<span id="optionele-brandlagen"></span>
<span id="toml-configuratie"></span>

<span id="proef-met-eigen-gebied-en-brandlagen"></span>

## Test met eigen gebied en brandlagen

Brandlagen zijn aanvullende lagen die het rekenhoogtemodel aanpassen om de
afstroming te sturen. De ingestelde verlagingen zijn geen werkelijke waterbodemhoogtes.
Deze test gebruikt BGT, TOP10NL en OSM voor een selectie van 1 × 1 km.
Daarmee wordt één kerntegel van 10 × 10 km berekend, met een rekengebied van
14 × 14 km inclusief buffer.

<span id="1-brandlagen-downloaden-en-voorbereiden"></span>
<span id="2-de-toml-opslaan"></span>

### 1. De voorbeeld-TOML opslaan

[Download de voorbeeld-TOML met BGT, TOP10NL en OSM](../reference/voorbeelden/brandlagen.toml).
Sla deze op als `invoer/brandlagen.toml`, gerekend vanaf de map met `pixi.toml`.
De bronpaden worden vanaf de TOML gelezen en verwijzen naar `../data/source_data/`
en `../data/processed_data/`.

| Openbare bron | Opgenomen laagtypen |
| --- | --- |
| BGT | Watervlakken en duikers uit kunstwerkdelen. |
| TOP10NL | Watervlakken en waterlijnen. |
| OSM | Kanalen, sloten, afvoerwatergangen, beken en duikers. |

<span id="2-instellingen-aanpassen"></span>

### 2. Instellingen aanpassen (optioneel)

De voorbeeld-TOML is voor deze test ongewijzigd bruikbaar als u deze op de
hierboven genoemde locatie opslaat. De TOML bepaalt welke aanvullende lagen in
de berekening worden gebruikt. `openbare_bron = "bgt"`, `"top10nl"` of `"osm"`
schakelt de automatische bronvoorbereiding in; `bron` geeft bij duikers hun
herkomst aan. De bronnen moeten het rekengebied inclusief buffers dekken.
BGT en OSM worden gebiedsgericht opgehaald voor het rekengebied inclusief
buffers. TOP10NL gebruikt het landelijke GeoPackage.

Met `brandwaarde` stelt u in hoeveel een aanvullende brandlaag het rekenhoogtemodel
verlaagt of verhoogt. Een negatieve waarde verlaagt; een positieve waarde verhoogt.

In de voorbeeld-TOML staat onder `[defaults]` een verlaging van 10 meter (`-10.0`).
Die geldt tenzij bij de laag een andere waarde staat. Zo gebruikt TOP10NL `-5.0`:
een verlaging van 5 meter. Een waarde bij een afzonderlijk bronobject heeft
voorrang op beide instellingen.

Deze instellingen gelden alleen voor aanvullende brandlagen. De aparte
inbrandregels voor waterlopen en duikers uit HyDAMO en Rijkswateren blijven gelden.

Voor BGT-wegdelen staat een uitgecommentarieerd voorbeeld in de TOML. Verwijder
de commentaartekens van dat blok om het te gebruiken. Vul bij `path` een pad
voor het bronbestand in en kies de `brandwaarde` en `prioriteit`. Een positieve
brandwaarde is een instelbare verhoging; de voorbeeldwaarde is geen advies.

Geschikte bronnen worden hergebruikt. Bewaar de bijbehorende JSON-bestanden en
raadpleeg het log voor de gebruikte bestanden. Zie
[opslag en hergebruik van openbare brandbronnen](configuratie.md#openbare-brandbronnen)
voor de cachevoorwaarden.

Voor **eigen bestanden** laat u `openbare_bron` weg en stelt u `path` en `layer`
in. Deze bestanden moeten vooraf aanwezig zijn en het rekengebied dekken.
Lijn- en vlakgeometrieën worden ondersteund, met een bekend coördinatenstelsel.
De automatische BGT-duikerselectie behoudt beide typen wanneer ze in de bron voorkomen.
Ook voor `prioriteit` hebben waarden bij objecten in het GeoPackage voorrang
op de TOML.
Zie [optionele brandlagen](../bewerkte-lagen/afwateringseenheden.md#optionele-brandlagen)
voor de overlapregels en het effect op de afstroming.

### 3. De productie starten

Start de test; ontbrekende openbare bronnen worden eerst opgehaald en voorbereid:

```console
pixi run --locked afwateringseenheden --bounds 184285 392054 185285 393054 --brandlagen-config ./invoer/brandlagen.toml --workers 1 --run-id brandtest
```

De grenzen staan in het project-CRS, standaard RD (`EPSG:28992`). De uitvoer
wordt niet op de rechthoek afgeknipt. Zie [eigen rechthoekig gebied](cli.md#eigen-rechthoekig-gebied).
Bekijk daarna de invoer en de daadwerkelijke inbranding zoals beschreven bij
[Resultaten bekijken en controleren](#resultaten-bekijken-en-controleren).

<span id="doelmodi-en-bronnen"></span>
<span id="duikers-sifons-en-hevels"></span>
<span id="waterlopen-en-duikers"></span>

## Aanvullende instellingen

Algemene opties staan bij [gedeelde productiecommando's](cli.md#opties).

??? info "Opties voor afwateringseenheden"

    | Optie | Gebruik |
    | --- | --- |
    | `--eigen-hydamo PAD` | Vervang de GKW-gegevens van het gekozen waterschap door een eigen HYDAMO-GeoPackage. Vereist een waterschapselectie. |
    | `--overige-waterschappen` | Neem ook afwateringsdoelen van andere waterschappen mee. Vereist een waterschapselectie; RWS blijft uitgesloten als doel. |
    | `--rijkswateren-url URL` | Gebruik een ander downloadadres voor de [Rijkswaterenbron](../bronlagen/rijkswateren.md). |
    | `--duiker-tolerance METERS` | Koppelafstand per duikeruiteinde tot primaire waterlopen; standaard 0,5 m. |
    | `--max-aansluitlengte METERS` | Sluit ook directe aansluitstukken tot deze lengte uit als afwateringsdoel. Standaard worden deze niet extra uitgesloten. |

    HYDAMO-duikers worden gelezen uit `duikersifonhevel`; RWS-duikers alleen als
    die laag in de Rijkswaterenbron zit. Zie
    [afwateringsdoelen](../bewerkte-lagen/afwateringseenheden.md#afwateringsdoelen)
    en [waterlopen en duikers](../bewerkte-lagen/afwateringseenheden.md#waterlopen-en-duikers-inbranden)
    voor de werking.

<span id="eigen-levering"></span>

??? info "Eisen aan een eigen HYDAMO-levering"

    - De lagen `hydroobject`, `gemaal`, `stuw` en `duikersifonhevel` zijn aanwezig,
      elk met een bekend coördinatenstelsel. Kunstwerklagen mogen leeg zijn.
    - Elk object heeft een geldig `nen3610id` van het gekozen waterschap.
    - Waterlopen hebben een categorie in `categorieoppwaterlichaam` of
      `categorieoppervlaktewater`: `primair`, `secundair`, `tertiair` of `overig`.

    Ontbrekende gegevens van het gekozen waterschap worden niet uit GKW aangevuld.
    Voor omliggende waterschappen blijft GKW de bron.

Voor eigen Python-workflows is er een
[bestaand voorbeeld](../reference/bewerkte-lagen-produceren.md#afwateringseenheden).

## Hervatten

Hervat de voorbeeldrun met dezelfde gebiedskeuze en runnaam:

```console
pixi run --locked afwateringseenheden --waterbeheercode 38 --workers 8 --run-id test --resume
```

Hervat een run met brandlagen door de oorspronkelijke opdracht, inclusief
`--brandlagen-config` met dezelfde configuratie, te herhalen met `--resume`.

Bewaar de runmap, inclusief `berekening/` en de overige tussenbestanden.
Bewaar ook de gebruikte brandbronnen en hun bronmetadata. Bij hervatten worden
openbare brandbronnen niet opnieuw gedownload of aangemaakt.
Geldige resultaten worden hergebruikt. Gewijzigde bronnen of rekeninstellingen
vereisen een nieuwe run-ID; bewerk invoer niet tijdens een berekening.
Zie [productiemappen](configuratie.md#productiemappen) voor alle
compatibiliteitsvoorwaarden.
