---
editorial_status: ai
---

# #65 — Configureerbare brandlagen

**Status:** geïmplementeerd op `issue/65_brandlagen`, ter review in
[PR #79](https://github.com/d2hydro/waterlagen/pull/79).
De onderstaande afspraken vormen het acceptatiecontract voor de implementatie.

Issue: [#65 Brandlaag](https://github.com/d2hydro/waterlagen/issues/65).
Uitvoering: eerste afzonderlijke branch en PR uit het
[gezamenlijke overzicht](index.md).

## Uitvoeringsverslag

- `Brandlaag`, `BrandlagenConfig`, `read_brandlagen_config` en `read_brandlagen`
  zijn publiek beschikbaar; de productie ondersteunt `--brandlagen-config`.
- De voorbereiding schrijft een gevalideerde lokale selectie met bronherkomst.
  Workers lezen hun eigen selectie en herhalen de gezamenlijke controle niet.
- Zowel DEM- als tegelhergebruik volgt bronidentiteit, defaults en brandbeleid.
  Een onderbroken herberekening krijgt geen geldige tegelcachemarkering.
- De bestaande gridhelper gebruikt de al gecontroleerde gehele celafmetingen,
  zodat afrondingsruis bij verschoven oorsprongen geen extra rastercel toevoegt.
- De relevante afwateringseenheden-, CLI- en voorbeeldsuite is uitgevoerd:
  189 tests geslaagd. Na aanvullende randgevallen en een correctie voor NoData
  na floatafronding zijn alle 44 brandlaag- en rastertests opnieuw geslaagd.
  Ruff en de strikte MkDocs-build slagen eveneens.
- Productie-instructies, API-referentie, Python-voorbeeld en een TOML-voorbeeld
  zijn bijgewerkt. Er zijn geen externe productiedatasets gedownload.

Documentatiebevinding: de beschermde functionele pagina
[Afwateringseenheden](../../bewerkte-lagen/afwateringseenheden.md) beschrijft
alleen de vaste brandbewerking. Uitleg over optionele relatieve wijzigingen,
voorrang, tekenconflicten en de scheiding van afwateringsdoelen ontbreekt daar
nog. De pagina is vanwege `editorial_status: human` niet aangepast.

## Doel en scope

Laat een gebruiker lijnen en polygonen in QGIS voorzien van brandwaarden en
prioriteiten. Combineer aangewezen lagen uit meerdere GeoPackages met een
publieke inleesfunctie tot één genormaliseerd, gesorteerd GeoDataFrame. Gebruik
deze invoer om de hoogte voor de afwateringsberekening relatief te wijzigen.

Ondersteun zowel Python-bouwstenen als de gewone productie-ingang. Het
automatisch verzamelen of afleiden van wegen, stuwen, duikers of Rijkswateren
behoort niet tot deze PR. #53 verzorgt zijn eigen bronvoorbereiding.

Absolute doelhoogtes zijn buiten scope. Houd de verwerking expliciet genoeg om
die later toe te voegen, zonder nu een algemeen bewerkingsframework te bouwen.
Brandlagen wijzigen geen afwateringsdoelen, segmentidentiteiten of netwerkverbindingen.

## Bestaand gedrag dat behouden blijft

`afwateringseenheden/raster.py` brandt nu primaire hydroobjecten met
`-2 * burn_depth_m` en secundaire hydroobjecten met `-burn_depth_m`.
Primair wint bij overlap, zonder optelling. De standaardproductie gebruikt
`burn_depth_m=100`: primair dus -200 m en secundair -100 m. Dit zijn
rekenkundige ingrepen; presenteer ze niet als gemeten waterbodemhoogtes.

Zonder optionele brandlagen moet hetzelfde resultaat blijven ontstaan. Ook
met optionele lagen blijft de rangorde **primair > secundair > optioneel**
onvoorwaardelijk gelden. De onderlinge volgorde van primaire en secundaire
lagen is niet instelbaar via optionele prioriteiten.

Behoud rastergrid, CRS, schaal, offset, dtype, NoData en bestaande
uitvoereigenschappen. Branden mag geen geldige hoogte buiten de brondekking maken.

## Attributen en defaults

| Attribuut | Betekenis |
| --- | --- |
| `brandwaarde` | Eindige relatieve hoogtewijziging in meters; negatief verlaagt, positief verhoogt. |
| `prioriteit` | Geheel getal; een hoger getal heeft voorrang binnen de optionele objecten. |

Waarden gelden per object. Los ieder attribuut afzonderlijk op in deze volgorde:

1. Een ingevulde objectwaarde.
2. De default voor de betreffende bronlaag.
3. De globale default.
4. Een validatiefout als de waarde nog ontbreekt.

Een ontbrekende kolom of QGIS `NULL` gebruikt de fallback. Een volledig ingevulde
laag heeft geen default nodig. Een ingevuld getal `0` is geen ontbrekende waarde.
Een ongeldige ingevulde waarde wordt afgewezen, niet stilzwijgend vervangen.
Er is geen impliciete globale brandwaarde of prioriteit.

Brandwaarde 0 is geldig: een object met hogere prioriteit kan daarmee een lagere
optionele brandbewerking blokkeren zonder zelf hoogte te veranderen. Bij gelijke
prioriteit verliest 0 van een grotere absolute waarde. Prioriteit 0 is eveneens geldig.

## Overlap en rasterisatie

Selecteer per rastercel de winnende optionele brandwaarde:

1. De hoogste prioriteit wint.
2. Bij dezelfde prioriteit wint de grootste absolute brandwaarde:
   -3 wint van -1; +4 wint van +2.
3. Positieve en negatieve waarden met dezelfde prioriteit op dezelfde rastercel
   vormen een fout, ook als een andere prioriteit of vaste laag die cel overstemt.
4. Nul is bij deze tekencontrole noch positief, noch negatief.
5. Gelijke prioriteit en gelijke brandwaarde leveren hetzelfde effect;
   bestands- of rijvolgorde mag de hoogte-uitkomst niet veranderen.

Pas de gekozen wijziging eenmaal op het oorspronkelijke, voorbereide reken-DEM
toe. Brandwaarden worden niet opgeteld. Pas de vaste primaire en secundaire
voorrang toe zonder de optionele waarden daarbij op te tellen.

Behoud de bestaande rasterisatie met `all_touched=False`: polygonen volgen
celcentrumselectie, lijnen de lijnrasterisatie. Voeg geen automatische lijnbuffer
toe. Voor een expliciete fysieke breedte levert de gebruiker een polygoon aan.
Ondersteun lijnen en polygonen, inclusief hun multipartvarianten.

## Controle vooraf en herkomst

Bewaar voor elk object het bronbestand, de laagnaam en de oorspronkelijke
GeoPackage-FID. Gebruik geen nieuwe concat-index als vervanging van die FID.

Controleer invoer en verzamel fouten vóór de zware afwateringsberekening. Meld
gevonden fouten gezamenlijk met de betrokken bestanden, lagen en FIDs, zodat
de gebruiker ze in één QGIS-ronde kan herstellen. Rapporteer een onleesbare bron
naast fouten uit andere bronnen die wel konden worden onderzocht.

Controleer tekenconflicten op gedeelde rastercellen binnen het gekozen rekengebied
inclusief tegelbuffers. Gebruik exact dezelfde grids en rasterisatieregels als
de berekening. Geometrische intersectie alleen is onvoldoende: twee geometrieën
kunnen dezelfde cel raken zonder elkaar te raken.

De conflictcontrole is onafhankelijk van later gelezen AHN-dekking en van
overstemmende lagen. Ze kan dus plaatsvinden voordat AHN-hoogtes worden gelezen.
Gebruik ruimtelijke selectie en lokale rastervensters; maak geen landelijk
controle-raster. Verzamel betrokken bronobjecten zonder dubbelrapportage door
overlappende tegelbuffers. Garandeer geen constante of altijd korte controletijd.

## Python en productieconfiguratie

Voeg kleine, expliciete configuratieobjecten toe voor bronpad/laagnaam,
laagdefaults, globale defaults en de verzameling bronnen. Gebruik dataclasses
waar vaste gegevensvelden nodig zijn; behoud bestaande publieke aanroepen.

De publieke leesfunctie levert één GeoDataFrame in `settings.crs`, gesorteerd
op oplopende prioriteit en vervolgens absolute brandwaarde, zodat de latere
winnaar bij vervangende rasterisatie voorrang krijgt. De tekencontrole staat los
van deze sortering. Voeg herkomst toe voor diagnostiek en reproduceerbaarheid.

Gebruik `waterlagen._geopandas.read_file` en bestaande CRS-helpers. Bij ruimtelijk
uitlezen moet de selectie eerst naar de bron-CRS worden getransformeerd; pas geen
bbox in project-CRS rechtstreeks toe op een bron in een andere CRS.

Voeg `--brandlagen-config PAD` aan de productie-CLI toe. Lees TOML met `tomllib`.
Het bestand bevat globale defaults en per bron het GeoPackage-pad, de laagnaam
en eventuele laagdefaults. De kolomnamen blijven `brandwaarde` en `prioriteit`.
Los relatieve bronpaden op ten opzichte van het configuratiebestand.

Gebruik dezelfde configuratie in Python en CLI. Bouw geen algemene nieuwe
configuratievoorziening. Bestaande `run_cli(..., transform=...)`-aansluiting kan
de productspecifieke optie vertalen. Neem een klein TOML-voorbeeld en een
uitvoerbaar Python-voorbeeld op.

## Tegels, workers en hergebruik

Houd de huidige verwerking per tegel. Stuur geen landelijk GeoDataFrame met
iedere workeropdracht mee. De leesfunctie moet ook voor een lokale selectie
bruikbaar zijn. Voorkom dat iedere worker de volledige conflictcontrole herhaalt;
scheid eenmalige voorbereiding/validatie van de lokale toepassing.

Leg bronidentiteit, gekozen lagen, effectieve defaults en het brandbeleid vast
bij de productieparameters en bij de controle op hergebruik. Een wijziging moet
zowel de rastercache als de cache van afgeleide tegelresultaten ongeldig maken.
Alleen een nieuwe DEM-tag volstaat niet: de tegelworkflow kan bestaande
subcatchments hergebruiken voordat rastervoorbereiding wordt aangeroepen.

Bij ongewijzigde invoer blijft hergebruik met `overwrite=False` mogelijk.
Bij gewijzigde brandinvoer mogen oude resultaten niet stilzwijgend worden
teruggegeven. Behoud downloads en bronnen die niet door deze wijziging geraakt worden.

## Implementatiestappen

1. Inspecteer de bestaande helpers en voeg de brandconfiguratie, TOML-inleeslogica
   en publieke GeoDataFrame-inleesfunctie toe. `afwateringseenheden/config.py`
   en een gericht modulebestand voor brandlagen zijn logische locaties.
2. Voeg attribuutvalidatie, fallback en bronherkomst toe. Implementeer de
   eenmalige rastercelcontrole met dezelfde gridconstructie als de verwerking.
3. Breid `afwateringseenheden/raster.py` uit met de optionele wijzigingen en
   de vaste primaire/secundaire voorrang. Behoud schaalconversie en NoData.
4. Geef configuratie door via `afwateringseenheden/tiles.py`, de workeropdrachten,
   `afwateringseenheden/productie.py` en `scripts/afwateringseenheden.py`.
5. Maak hergebruik gevoelig voor brandinvoer op raster- en tegelniveau.
6. Exporteer de publieke bouwstenen via `afwateringseenheden/__init__.py` en
   voeg NumPy-docstrings, productie-instructies, TOML-voorbeeld en Python-voorbeeld toe.

De precieze interne helpernamen en TOML-sleutels zijn implementatiedetails;
houd ze eenvoudig en leg het uiteindelijke schema op één plek vast.

## Acceptatiecriteria en tests

- Zonder optionele bronnen blijft de bestaande standaarduitkomst behouden.
- Primair wint altijd van secundair; beide winnen van iedere optionele prioriteit.
- Positieve, negatieve en nulwaarden werken volgens de beschreven regels,
  zonder cumulatie of afhankelijkheid van invoervolgorde.
- NULL en ontbrekende kolommen gebruiken per attribuut de juiste fallback;
  onopgeloste of ongeldige waarden geven herkenbare fouten.
- Gelijke prioriteit kiest de grootste absolute waarde; tegengestelde tekens
  op dezelfde cel worden gezamenlijk gemeld, ook als ze worden overstemd.
- Controle omvat ook twee niet-kruisende geometrieën in dezelfde cel en
  conflicten in overlappende tegelbuffers, zonder dubbele foutmeldingen.
- Meerdere bestanden/lagen, multipartgeometrieën en een afwijkende bron-CRS
  leveren correcte selectie, herkomst en rasterisatie op.
- NoData blijft behouden; meters worden correct naar opgeslagen rastereenheden
  omgerekend. Ongeldige of niet-representeerbare waarden worden niet stil afgeknipt.
- Seriële en parallelle verwerking leveren dezelfde resultaten; workers herhalen
  de volledige preflight niet en ontvangen niet telkens de landelijke gegevens.
- Gewijzigde brandwaarden, defaults of bronnen maken raster- en tegelhergebruik
  ongeldig; ongewijzigde invoer blijft herbruikbaar.
- CLI en Python gebruiken hetzelfde schema. Relatieve TOML-paden werken
  onafhankelijk van de actuele werkdirectory.

Gebruik kleine synthetische GeoPackages en rasters, zonder netwerkverkeer.
Breid de relevante tests voor rasters, tegels, workers, productie en voorbeelden
uit; voeg gerichte tests voor de nieuwe inleesfunctie en configuratie toe.
Voer deze uit met `pixi run pytest <test-bestanden>`, controleer gewijzigde Python
met Ruff en bouw documentatie met `pixi run --environment docs docs-build`.
Voor het voorbeeld geldt ook `pixi run pytest tests/test_python_examples.py`.

## Documentatie-impact en afhankelijkheden

Documentatie-impact: **confirmed**. Werk de bewerkbare
[productie-instructies](../../produceren/afwateringseenheden.md),
[API-referentie](../../reference/afwateringseenheden.md) en voorbeelden bij.
De functionele pagina [Afwateringseenheden](../../bewerkte-lagen/afwateringseenheden.md)
is beschermd met `editorial_status: human`. Rapporteer de benodigde uitleg over
optionele brandlagen, prioriteiten en beperkingen afzonderlijk; wijzig die pagina
uitsluitend met expliciete toestemming.

#53 mag voorbereide Rijkswateren als gewone optionele bron aanleveren, zonder
een aparte brandroutine. [#67](issue-67-duikers.md) sluit duikertrajecten in
primaire hydroobjecten uit van de primaire brandwerking en de afwateringsdoelen,
terwijl korte aansluitstukken wel gebrand kunnen blijven zonder doeltoekenning.
Houd deze geometrieselecties afzonderlijk. Secundaire en optionele brandlagen
blijven ook op duikertrajecten toegestaan. Toets de afspraken opnieuw na
afronding van dat ontwerp.
