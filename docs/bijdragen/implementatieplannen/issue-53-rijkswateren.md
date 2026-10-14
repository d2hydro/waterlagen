---
editorial_status: ai
---

# #53 — Rijkswateren gebruiken als brandlaag

**Status:** conceptplan. De scope en acceptatie zijn in het ontwerpgesprek
bevestigd; de gezamenlijke review met #65 en #67 volgt nog. Dit document
beschrijft gepland gedrag, geen reeds beschikbare functionaliteit.

Issue: [#53 Expliciet opnemen Rijkswateren](https://github.com/d2hydro/waterlagen/issues/53).
Uitvoering: afzonderlijke branch en PR na samenvoegen van
[#65 Configureerbare brandlagen](issue-65-brandlagen.md).

## Doel en afbakening

Gebruik een aangeleverde Rijkswaterenlaag om het reken-DEM langs die waterlopen
te verlagen. De laag wordt als gewone optionele brandlaag verwerkt via #65.
Rijkswateren krijgen in deze versie geen eigen afwateringsdoelen of
afwateringseenheden.

Deze PR bevat configuratie, gebruiksinstructies en gerichte verificatie.
Voeg geen tweede inleesfunctie, brandroutine of Rijkswateren-specifieke
vertakking in de rasterberekening toe als de generieke invoer uit #65 volstaat.
Een documentatie- en voorbeeldgerichte PR is voor deze beperkte scope voldoende.

De volgende onderdelen uit het oorspronkelijke issue zijn uitgesteld:

- automatisch downloaden van OSM-bronnen;
- selecteren en opwaarderen van OSM-objecten tot Rijkswateren-hydroobjecten;
- productiegeschikt maken van de bestaande voorbereidende code;
- verwijderen van overlappende hydroobjecten uit het beheerregister;
- Rijkswateren toevoegen als afwateringsdoelen.

De productie van hydroobjecten wordt in een ander issue opgepakt. Verzin geen
issueverwijzing zolang dat issue niet bekend is. Beschrijf de beperkte afronding
expliciet in de PR; claim niet dat alle oorspronkelijke checklistonderdelen zijn
geïmplementeerd.

## Beschikbare invoer

De bestaande voorbereidende code in
[`d2hydro/rws_hydroobject`](https://github.com/d2hydro/rws_hydroobject)
schrijft `data/hydroobject.gpkg`, laag `hydroobject`. De betreffende
`bouw_hydroobjecten.py` schrijft LineStrings met onder andere `globalid`,
`nen3610id`, `objectid`, `categorieoppervlaktewater`, `naam`, `bron`,
`osm_id` en `osm_laag`.

De gegevensbestanden zijn niet in die repository meegeleverd. Er is in de
aangetroffen code geen downloadvoorziening of expliciete CRS-controle. De code
is achtergrond voor het invoercontract; porteren of uitvoeren daarvan hoort
niet bij deze PR. Behandel de onvolledige bronvoorbereiding niet als gevalideerde
landelijke dekking.

Gebruik een door de gebruiker aangeleverd bestand met bekende herkomst en CRS.
De generieke validatie uit #65 controleert de gegevens vóór verwerking.
Een ontbrekende CRS mag niet stilzwijgend als `EPSG:28992` worden geïnterpreteerd.

`brandwaarde` en `prioriteit` ontbreken in de bestaande uitvoer. Vul ze aan via
de laagdefaults uit de TOML-configuratie. De gebruiker kan de attributen later
in QGIS toevoegen en per object afwijken.

Het bronattribuut `categorieoppervlaktewater="primair"` maakt deze objecten
in deze toepassing niet tot de vaste primaire brandlaag. De invoer wordt
uitsluitend als optionele brandlaag gebruikt, zonder opname in het
watersysteem of het afwateringsdoelraster.

## Brandinstellingen en overlap

Gebruik dezelfde relatieve verlaging als de primaire waterlopen:
`brandwaarde = -2 * burn_depth_m`. Bij de huidige standaardproductie met
`burn_depth_m=100` bevat het configuratievoorbeeld dus `brandwaarde = -200`.
Dit is een rekenkundige verlaging, geen uitspraak over de werkelijke bodemhoogte.

Gebruik `prioriteit = 0` als begininstelling voor deze optionele laag.
De waarden blijven aanpasbaar via laagdefaults en de QGIS-attributen volgens
het contract van #65. Het TOML-voorbeeld bevat getallen, geen formule-evaluatie;
bij een afwijkende primaire branddiepte moet de voorbeeldwaarde overeenkomstig
worden aangepast om dezelfde verlaging te behouden.

De vaste rangorde blijft **primair > secundair > optioneel**. Een Rijkswaterlijn
met brandwaarde -200 m verliest dus op een overlappende cel van de vaste
secundaire waterloop, ook als die slechts -100 m wordt verlaagd. Branddiepte en
voorrang zijn verschillende instellingen. Tel waarden niet op en verwijder
geen beheerregisterobjecten om de optionele laag te laten winnen.

## Implementatiestappen

1. Controleer na samenvoegen van #65 dat de generieke inleesfunctie de
   aangeleverde lijnlaag zonder `brandwaarde` en `prioriteit` accepteert met
   expliciete laagdefaults. Hergebruik de bestaande CRS- en invoercontrole.
2. Voeg een klein TOML-gebruiksvoorbeeld toe voor `hydroobject.gpkg`, laag
   `hydroobject`, met brandwaarde -200 en prioriteit 0. Gebruik een relatief
   voorbeeldpad, opgelost ten opzichte van het configuratiebestand.
3. Documenteer het aanleveren van de lokale bron en de productieaanroep via
   `--brandlagen-config`. Vermeld dat het voorbeeldbestand zelf geen
   Rijkswaterengegevens downloadt of bevat.
4. Voeg gerichte verificatie toe voor toepassing van de configuratie en de
   combinatie met de vaste lagen. Hergebruik tests uit #65; dupliceer geen
   volledige testsuite voor de generieke brandregels.
5. Voer de onderstaande menselijke vergelijking uit met de aangeleverde
   bron vóór inhoudelijke acceptatie van deze PR.

## Technische acceptatiecriteria

- De bronlaag wordt via dezelfde publieke functies als iedere andere
  optionele brandlaag verwerkt.
- Bij ontbrekende brandattributen werken de expliciete laagdefaults.
- Zonder vaste of hoger geprioriteerde optionele overlap verlaagt de
  standaardconfiguratie de geraakte cellen met 200 m.
- De aanwezigheid van `categorieoppervlaktewater="primair"` in deze bron
  verandert de vaste rangorde niet.
- Bij overlap met primaire of secundaire waterlopen blijft het effect van
  die vaste laag ongewijzigd ten opzichte van de berekening zonder Rijkswateren.
- Het segmentraster en de verzameling afwateringsdoelen veranderen niet door
  het toevoegen van deze brandlaag. Afgeleide afwateringseenheden kunnen door
  de gewijzigde stromingsberekening wel veranderen.
- Hergebruik reageert op gewijzigde brongegevens of brandinstellingen volgens
  het cachecontract uit #65.

Gebruik een kleine synthetische GeoPackage met dezelfde relevante invoervorm,
zonder netwerkverkeer of echte landelijke bestanden. Voer de gerichte tests
uit met `pixi run pytest <test-bestanden>`. Controleer gewijzigde Python met Ruff
indien code of voorbeelden worden aangepast. Bouw documentatie met
`pixi run --environment docs docs-build`.

## Inhoudelijke acceptatie

Vergelijk een productie zonder en met de Rijkswaterenlaag bij de Maas en de
Brabantse kanalen in het gebied van Aa en Maas. Gebruik dezelfde bronversies,
gebieden en overige rekeninstellingen. Leg ten minste vast:

- welk bronbestand, welke laag en welke brandinstellingen zijn gebruikt;
- of de gewenste Rijkswaterlijnen aanwezig zijn en correct worden verlaagd;
- of overlap met bestaande primaire en secundaire lijnen hun effect behoudt;
- hoe stroomrichtingen en afwateringseenheden veranderen nabij de Rijkswateren;
- of nieuwe gaten, ongewenste afvoer of andere onbedoelde grensverschuivingen
  zichtbaar worden.

De gebruiker beoordeelt deze kaarten inhoudelijk. Een aantoonbaar verdiept
raster bewijst op zichzelf geen betere hydrologische afbakening. Rapporteer
tekortkomingen van de beperkte aanpak, zonder tijdens deze PR alsnog een
OSM-productieketen of eigen Rijkswateren-afwateringsdoelen toe te voegen.

De echte bron is een externe voorwaarde voor deze kaartcontrole. Synthetische
tests mogen wel vooraf worden uitgevoerd; markeer de inhoudelijke controle
niet als voltooid zolang brongegevens of menselijke beoordeling ontbreken.

## Documentatie en aansluiting op #67

Documentatie-impact: **confirmed**. Beschrijf de aangeleverde Rijkswaterenbron
en de externe verwijzingen op een eigen bronpagina onder `docs/bronlagen/`.
Vermeld daar de onvolledige voorbereiding en de scheiding met de toekomstige
automatische bronproductie. Verifieer externe URLs bij het schrijven daarvan.

De gebruiksinstructies horen bij de productie van afwateringseenheden en linken
naar die bronpagina. De functionele pagina
[Afwateringseenheden](../../bewerkte-lagen/afwateringseenheden.md) is beschermd
met `editorial_status: human`: rapporteer de benodigde aanvulling afzonderlijk
en wijzig die pagina uitsluitend met expliciete toestemming.

Deze PR introduceert geen nieuwe afwateringsdoelen. [#67](issue-67-duikers.md)
sluit duikertrajecten in primaire hydroobjecten uit van de primaire brandwerking
en van de afwateringsdoelen. Optionele brandlagen, waaronder deze Rijkswaterenlaag,
blijven op die trajecten toegestaan. Brandinvoer en doeltoekenning blijven
afzonderlijke functies; voeg hiervoor geen Rijkswateren-specifieke brandroutine toe.
