---
editorial_status: ai
---

# Afwateringseenheden produceren

## Starten

Volg eerst [Installatie](installatie.md). Open daarna een terminal in de map
waarin `pixi.toml` staat. Start bijvoorbeeld een run voor Aa en Maas:

```console
pixi run --locked afwateringseenheden --waterbeheercode 38 --workers 2 --run-id proef
```

Gebruikt u de broncode uit GitHub? Voeg dan bij de opdrachten op deze pagina
`--environment afwateringseenheden` toe na `pixi run`.

Ontbrekende standaardbronnen (AHN, HYDAMO, Rijkswateren en gebiedsgrenzen) worden
automatisch opgehaald en voorbereid. Bestaande bronnen worden hergebruikt;
met `--offline` moeten ze al lokaal beschikbaar zijn. Aanvullende bestanden
uit de brandlagen-TOML en een eventuele eigen HYDAMO-levering levert u zelf aan.

Ook een klein gebied kan volledige rekentegels en landelijke downloads vereisen.
Zie [gebieden](cli.md#gebieden) voor de beschikbare selecties en hun omvang.
Een bestaande runnaam wordt niet automatisch hergebruikt: kies een nieuwe naam
of [hervat de bestaande run](#hervatten).

<span id="uitvoer-en-hervatten"></span>
<span id="controle-in-qgis"></span>
<span id="brandlagen-controleren-in-qgis"></span>
<span id="afwateringseenheid-aan-een-segment-koppelen"></span>

## Resultaten bekijken en controleren

Bij standaardopslag staat de voorbeeldrun in
`data/processed_data/afwateringseenheden/waterschap_38/proef/`.
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

Zorg dat deze bestanden het volledige rekengebied dekken:

- `data/source_data/bgt/bgt.gpkg`, laag `bgt_waterdeel`.
- `data/source_data/top10nl/top10nl_Compleet.gpkg`, laag `top10nl_waterdeel_vlak`.

Voor BGT downloadt u de landelijke GML-light-ZIP via de
[BGT-bronpagina](../bronlagen/bgt.md#externe-verwijzingen) en volgt u
[BGT-vlakken voorbereiden](bgt-vlakken.md) om `bgt.gpkg` te maken.
Gebruik voor TOP10NL het [downloadvoorbeeld](../reference/bronlagen-downloaden.md#top10nl).

De lagen moeten geldige vlakgeometrieën en een bekend coördinatenstelsel hebben.
Voor dit voorbeeld zijn geen extra attributen nodig: `brandwaarde` en
`prioriteit` staan in de TOML. Zijn deze attributen al bij objecten ingevuld,
dan hebben die waarden voorrang.

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

Start de proef met deze configuratie:

```console
pixi run --locked afwateringseenheden --bounds 184285 392054 185285 393054 --brandlagen-config ./invoer/brandlagen.toml --workers 1 --run-id brandproef
```

De grenzen staan in het project-CRS, standaard RD (`EPSG:28992`). De uitvoer
wordt niet op de rechthoek afgeknipt. Zie [eigen rechthoekig gebied](cli.md#eigen-rechthoekig-gebied).
Bekijk daarna de invoer en de daadwerkelijke inbranding zoals beschreven bij
[Resultaten bekijken en controleren](#resultaten-bekijken-en-controleren).

[Download de uitgebreide voorbeeld-TOML](../reference/voorbeelden/brandlagen.toml)
voor meer lagen en instellingen. Deze gebruikt dezelfde locatie
`invoer/brandlagen.toml` en verwijst naar `../data/`.

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
pixi run --locked afwateringseenheden --waterbeheercode 38 --workers 2 --run-id proef --resume
```

Bewaar de runmap, inclusief `berekening/` en de overige tussenbestanden.
Geldige resultaten worden hergebruikt. Gewijzigde bronnen of rekeninstellingen
vereisen een nieuwe run-ID; bewerk invoer niet tijdens een berekening.
Zie [productiemappen](configuratie.md#productiemappen) voor alle
compatibiliteitsvoorwaarden.
