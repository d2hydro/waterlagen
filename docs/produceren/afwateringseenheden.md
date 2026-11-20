---
editorial_status: ai
---

# Afwateringseenheden produceren

<span id="starten"></span>

Kies **Afwateringseenheden** in de [Run Maker](index.md). De standaardbronnen worden automatisch opgehaald. Wilt u aanvullende lagen inbranden? Zie [extra brandlagen](#test-met-eigen-gebied-en-brandlagen).

<span id="uitvoer-en-hervatten"></span>
<span id="controle-in-qgis"></span>
<span id="brandlagen-controleren-in-qgis"></span>
<span id="afwateringseenheid-aan-een-segment-koppelen"></span>


## Resultaten bekijken en controleren

Open in QGIS de bestanden uit `data/processed_data/afwateringseenheden/<gebied>/<run-id>/`:

1. Open `afwateringseenheden.gpkg` en `watersysteem.gpkg` samen. Koppel een vlak via `segment_id` aan `hydroobject_segment` uit **dezelfde run**.
2. Bekijk in `controle.gpkg` de laag `niet_toegewezen` en de duikermeldingen. Een vlak kan bijvoorbeeld geen route naar een afwateringsdoel hebben.
3. Vergelijk voor een controle van de inbranding `brandlagen.gpkg` (geselecteerde invoer) met `berekening/tegels/<tegel>/brandbron.tif` (gebruikte bron per cel).

[Betekenis van de lagen en velden](../bewerkte-lagen/afwateringseenheden.md#uitvoer)

<span id="signaalkaart-beoordelen"></span>

**Signaalkaart.** Leg `signaalkaart.gpkg` over de afwateringseenheden. Beoordeel bij elke gemarkeerde BGT-duiker of er een verbinding in het watersysteem ontbreekt. De velden `id` en `bronhouder` verwijzen naar het BGT-object.

??? info "Hoe worden bestaande verbindingen herkend?"

    Alle actuele BGT-duikers tellen mee. Een lijn moet een grens kruisen en eindigen in twee verschillende eenheden. Een vlak moet aan beide kanten van een grens liggen.

    Een duiker valt af als minstens de helft van zijn lengte of oppervlak binnen 2 m van het gebruikte, verbonden waternet ligt. Voor de overige duikers wordt de route gecontroleerd. Bij lijnen tellen beide uiteinden, bij vlakken één punt per overlappende eenheid, het dichtst bij het doelsegment. Alleen als alle punten binnen 2 m van een gebruikte primaire waterloop liggen én alle betrokken doelen al verbonden zijn, valt de duiker alsnog af.

<span id="1-brandlagen-downloaden-en-voorbereiden"></span>
<span id="2-de-toml-opslaan"></span>
<span id="2-instellingen-aanpassen"></span>

<span id="1-de-voorbeeld-toml-opslaan"></span>
<span id="2-instellingen-aanpassen-optioneel"></span>
<span id="3-de-productie-starten"></span>
<span id="toml-configuratie"></span>
<span id="proef-met-eigen-gebied-en-brandlagen"></span>
<span id="optionele-brandlagen"></span>
<span id="test-met-eigen-gebied-en-brandlagen"></span>

## Extra brandlagen kiezen

Ga bij de extra opties naar **Brandlagen instellen**. Maak een nieuwe TOML of kies een bestaand bestand. Voor een openbare bron volstaat de bronnaam. Kies bij een eigen GeoPackage het bestand en de laag. Elke geselecteerde laag wordt ingebrand, ook een duiker zonder aansluiting op een waterloop.

[Download een voorbeeld-TOML](../reference/voorbeelden/brandlagen.toml){ .md-button .md-button--primary download="brandlagen.toml" }
[Hoogte en voorrang bij overlap](../bewerkte-lagen/afwateringseenheden.md#optionele-brandlagen){ .md-button }

??? info "De hoogte per rekencel kiezen"

    <span id="dem-resampling-kiezen"></span>

    Standaard gebruikt het rekenraster de laagste AHN-waarde (`min`) per cel van 2 × 2 meter. Met een andere methode kunnen ook de afwateringsgrenzen veranderen. Kies daarvoor een nieuwe runnaam.

<span id="doelmodi-en-bronnen"></span>
<span id="duikers-sifons-en-hevels"></span>
<span id="waterlopen-en-duikers"></span>

## Aanvullende instellingen

Open **HyDAMO en Rijkswateren** voor een eigen bron. Onder **Afstroming en duikers** staan de rekeninstellingen.

??? info "Opties voor afwateringseenheden"

    | Optie | Gebruik |
    | --- | --- |
    | `--eigen-hydamo PAD` | Vervang de GKW-gegevens van het gekozen waterschap door een eigen HYDAMO-GeoPackage. Vereist een waterschapselectie. |
    | `--overige-waterschappen` | Neem ook afwateringsdoelen van andere waterschappen mee. Vereist een waterschapselectie; RWS blijft uitgesloten als doel. |
    | `--rijkswateren-url URL` | Gebruik een ander downloadadres voor de [Rijkswaterenbron](../bronlagen/rijkswateren.md). |
    | `--duiker-tolerance METERS` | Koppelafstand per duikeruiteinde tot primaire waterlopen; standaard 0,5 m. |
    | `--max-aansluitlengte METERS` | Sluit ook directe aansluitstukken tot deze lengte uit als afwateringsdoel. Standaard worden deze niet extra uitgesloten. |
    | `--max-complex-routelengte METERS` | Maximale lengte per parallelle kunstwerkroute om interne hydroobjecten als doel uit te sluiten. Standaard 100 m; `0` schakelt deze regel uit. |

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

<span id="parallelle-routes-instellen"></span>

??? info "Wanneer vallen parallelle routes af als doel?"

    Met `--max-complex-routelengte` worden parallelle routes met elk een kunstwerk uitgesloten als afwateringsdoel, mits iedere volledige route maximaal 100 m lang is (instelbaar, 0 schakelt de regel uit).

    In de laag `watersysteem.gpkg:hydroobject_segment` zijn afwateringsdoelen blauw en uitgesloten segmenten oranje. Bij complexen met duikers, sifons of hevels worden de interne hydroobjecten ook niet ingebrand. Bij uitsluitend stuwen of gemalen blijft de inbranding behouden. Aansluitende waterlopen buiten de lus blijven ongemoeid.

## Hervatten

Gebruik dezelfde runnaam, bronbestanden en rekeninstellingen. Bewaar de volledige runmap, inclusief `berekening/`, en de brandbronnen met hun JSON.
