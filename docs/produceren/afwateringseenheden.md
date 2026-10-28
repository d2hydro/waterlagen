---
editorial_status: ai
---

# Afwateringseenheden produceren

## Starten

Volg eerst [Installatie](installatie.md). Open daarna een terminal in de map
waarin `pixi.toml` staat. Start bijvoorbeeld een run voor Aa en Maas:

```console
pixi run --locked afwateringseenheden --waterbeheercode 38 --workers 8 --run-id test
```

Gebruikt u de broncode uit GitHub? Voeg dan bij de opdrachten op deze pagina
`--environment afwateringseenheden` toe na `pixi run`.

Ontbrekende standaardbronnen (AHN, HYDAMO, Rijkswateren en gebiedsgrenzen) worden
automatisch opgehaald en voorbereid. Bestaande bronnen worden hergebruikt;
met `--offline` moeten ze al lokaal beschikbaar zijn. Aanvullende bestanden
uit de brandlagen-TOML en een eventuele eigen HYDAMO-levering levert u zelf aan.

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
[aandachtspunten en beperkingen](../bewerkte-lagen/afwateringseenheden.md#aandachtspunten-en-beperkingen)
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

## Proef met eigen gebied en brandlagen

Brandlagen zijn aanvullende lagen die het rekenhoogtemodel aanpassen om de
afstroming te sturen. De ingestelde verlagingen zijn geen werkelijke waterbodemhoogtes.
Deze proef gebruikt BGT-water en TOP10NL-water voor een selectie van 1 × 1 km.
Daarmee wordt één kerntegel van 10 × 10 km berekend, met een rekengebied van
14 × 14 km inclusief buffer.

### 1. Brandlagen downloaden en voorbereiden

De aanvullende bestanden uit de TOML moeten vóór de productie beschikbaar zijn.
Zorg dat ze het volledige rekengebied inclusief tegelbuffers dekken, niet alleen
de opgegeven bounds. Voor deze proef is dat de RD-rechthoek
`178000 388000 192000 402000`.

- **BGT:** volg [BGT-vlakken voorbereiden](bgt-vlakken.md#voorbereiden).
  Dit levert `data/source_data/bgt/bgt.gpkg` met laag `bgt_waterdeel`.
- **TOP10NL:** gebruik het [downloadvoorbeeld](../reference/bronlagen-downloaden.md#top10nl)
  en [download het script](../reference/voorbeelden/download_top10nl.py).
  Met `DATA_DIR = Path("data")` levert dit
  `data/source_data/top10nl/top10nl_Compleet.gpkg` met laag `top10nl_waterdeel_vlak`.

**Optioneel: OSM-waterlopen en duikers.** Download deze ook vooraf als u ze als
brandlagen wilt gebruiken. Zie [OSM-kanalen](../reference/bronlagen-downloaden.md#osm-kanalen)
en het [downloadscript](../reference/voorbeelden/download_osm_canals.py).
Stel daarin `DATA_DIR` (gegevensmap) en `BOUNDS` (downloadgebied in RD) in.
Gebruik voor deze proef `BOUNDS = (178000, 388000, 192000, 402000)`;
dit omvat de volledige kerntegel met buffer.
Met `DATA_DIR = Path("data")` komen de vijf GeoPackages in `data/source_data/osm/`.
Gebruik voor opname van deze lagen de
[uitgebreide voorbeeld-TOML](../reference/voorbeelden/brandlagen.toml).

Een `.py`-bestand downloaden haalt alleen het script op. Voer het daarna uit
om de brongegevens op te halen; zie [Een script uitvoeren](../reference/gebruik.md#een-script-uitvoeren)
voor starten met `pixi run`.

### 2. De TOML opslaan

De BGT- en TOP10NL-waterlagen in het onderstaande minimale voorbeeld moeten
geldige vlakgeometrieën en een bekend coördinatenstelsel hebben.
Voor dit voorbeeld zijn geen extra attributen nodig: `brandwaarde` en
`prioriteit` staan in de TOML. Zijn deze attributen al bij objecten in het
GeoPackage ingevuld, dan hebben die waarden voorrang.

Sla het volgende bestand op als `invoer/brandlagen.toml`, gerekend vanaf de map
met `pixi.toml`. De relatieve bronpaden worden vanaf de TOML gelezen en verwijzen
dus naar `data/source_data`. Pas ze aan als uw bronnen ergens anders staan.

```toml
[[lagen]]
path = "../data/source_data/bgt/bgt.gpkg"
layer = "bgt_waterdeel"
rol = "water"
brandwaarde = -10.0
prioriteit = 2

[[lagen]]
path = "../data/source_data/top10nl/top10nl_Compleet.gpkg"
layer = "top10nl_waterdeel_vlak"
rol = "water"
brandwaarde = -5.0
prioriteit = 0
```

De ingestelde verlaging is 10 m voor BGT-water en 5 m voor TOP10NL-water.
Zie [optionele brandlagen](../bewerkte-lagen/afwateringseenheden.md#optionele-brandlagen)
voor de overlapregels en het effect op de afstroming.

[Download de uitgebreide voorbeeld-TOML](../reference/voorbeelden/brandlagen.toml)
voor meer lagen en instellingen. Sla deze ook op als `invoer/brandlagen.toml`;
de bronpaden verwijzen naar `../data/`. Neem alleen lagen op waarvoor u de
benodigde bestanden hebt voorbereid.

### 3. De productie starten

Start de proef met deze configuratie:

```console
pixi run --locked afwateringseenheden --bounds 184285 392054 185285 393054 --brandlagen-config ./invoer/brandlagen.toml --workers 1 --run-id brandproef
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

Bewaar de runmap, inclusief `berekening/` en de overige tussenbestanden.
Geldige resultaten worden hergebruikt. Gewijzigde bronnen of rekeninstellingen
vereisen een nieuwe run-ID; bewerk invoer niet tijdens een berekening.
Zie [productiemappen](configuratie.md#productiemappen) voor alle
compatibiliteitsvoorwaarden.
