# Functioneel landgebruik produceren

Het productiepakket bevat `scripts/functioneel_landgebruik.py` voor het maken
van een landelijk raster met functionele landgebruiksklassen. De betekenis van
de klassen, bronnen en bewerkingen staat bij
[Functioneel landgebruik](../bewerkingen/functioneel-landgebruik.md).

## Vooraf

De losse rasterfunctie en de parallelle tegelverwerking gebruiken dezelfde
standaardbronnen uit de datastore. Als `source_data/hydamo/hydamo.gpkg`
aanwezig is, worden de gemalen meegenomen. Met een expliciet `sources`-object
bepaal je zelf de bronpaden; `gemalen_gpkg=None` slaat gemalen over.

Bij parallelle productie staan de detailmeldingen per tegel in
`tiles/logs/<rasterbestandsnaam>.log`. Dit omvat ontbrekende CSV-koppelingen
met bronlaag, veld en aantallen per bronwaarde, overgeslagen bronnen,
rekentijd en eventuele foutdetails. Deze worker-meldingen verschijnen niet
tussen de voortgangsbalk in de terminal. Afgeronde tegels en fouten blijven
zichtbaar in de hoofdvoortgang en, indien ingesteld, het productielog.

Voor de BAG-koppeling maakt de verwerking eenmalig `bag-light.pand_vbo.sqlite`
naast `bag-light.gpkg`. Dit is een afgeleid zoekbestand; de oorspronkelijke BAG
blijft ongewijzigd. De bronmap moet hiervoor schrijfbaar zijn. Bij landelijke
productie wordt dit bestand vóór het starten van de workers opgebouwd, met
voortgang in de log. Daarna hergebruiken alle workers dezelfde index.
Een gewijzigde bestandsgrootte of wijzigingsdatum van de BAG leidt tot opnieuw
opbouwen. Bij handmatige vervanging met behoud van beide kenmerken moet je
het zoekbestand verwijderen. Het mag opnieuw worden gemaakt en hoort niet in Git.

De index versnelt het vinden van verblijfsobjecten per pand. De functiekeuze,
oppervlakteberekening en omgang met gedeelde verblijfsobjecten blijven gelijk.

Volg [Installatie](installatie.md) en controleer het productiepakket met
`pixi run --locked controleer`. Gegevens komen standaard onder `./data` in de
projectfolder; zie [Opslag van gegevens](configuratie.md) voor een andere locatie.

Dit voorbeeld verwerkt een landelijk tegelrooster. Downloads en berekeningen
kunnen veel schijfruimte en tijd vragen. Controleer de instellingen in het
script en de functionele beschrijving voordat u de productie start.

## Starten

Bereid de BGT eenmalig voor met [BGT-vlakken voorbereiden](bgt-vlakken.md).
Het landgebruikscript gebruikt dit bestand en maakt geen tweede BGT-GeoPackage.

Open PowerShell in uw projectfolder
en voer uit:

```powershell
pixi run --locked landgebruik
```

De taak voert het meegeleverde script uit. Rechtstreeks starten kan ook:

```powershell
pixi run --locked python ./scripts/functioneel_landgebruik.py
```

Alle productie-instellingen staan bovenaan `scripts/functioneel_landgebruik.py`:

| Instelling | Huidige waarde |
|---|---|
| `WORKERS` | 32 |
| `RESOLUTION_M` | 0,5 meter |
| `TEGELGROOTTE_M` | 5.000 meter |
| `UITVOERMAP` | `functioneel_landgebruik_20260925_actuele_bgt` |
| `BGT_BESTAND` | `bgt.gpkg` |
| `TEGELS_OVERSCHRIJVEN` | `True`: rastertegels opnieuw berekenen |
| `COG_OVERSCHRIJVEN` | `False`: bestaande landelijke TIFF behouden |
| `CONTROLE_OPSLAAN` | `True`: NoData-controle schrijven |

Het script hergebruikt het tegelrooster en de voorbereide actuele BGT. De BGT
moet de vijf gebruikte lagen en de einddatumvelden bevatten. De gebruikte CSV
wordt in de uitvoermap bewaard; bij een afwijkende CSV moet u een nieuwe
uitvoermap kiezen.

Bij conversie van BGT-wegdelen en terreindelen wordt tijdelijk één GML-laag
naast het doelbestand uitgepakt. Houd ruimte vrij voor de grootste uitgepakte
laag, naast het nieuwe GeoPackage. Dit is nodig om alle attributen te behouden
en expliciet `geometrie2d` te gebruiken in plaats van een kruinlijn. De bestaande
ZIP kan worden hergebruikt. Alleen het script opnieuw starten herstelt een
eerder verkeerd omgezet GeoPackage niet: dat bronbestand wordt hergebruikt.

Let op: met `COG_OVERSCHRIJVEN=False` wordt een bestaande landelijke TIFF niet
vernieuwd na het herberekenen van tegels. De VRT verwijst wel naar die tegels.
Zet deze instelling op `True` als ook de bestaande landelijke TIFF moet worden vernieuwd.

## Resultaten

Onder `processed_data/<UITVOERMAP>` in uw datastore vindt u:

- `tiles/`: de berekende rastertegels;
- `functioneel_landgebruik.vrt`: de tegels samengevoegd als virtueel raster;
- `functioneel_landgebruik.tif`: het samengestelde Cloud Optimized GeoTIFF-raster.
- `functioneel_landgebruik.qml`: legenda voor het landelijke raster in QGIS;
- `nodata.gpkg`: NoData-vlakken met bron en reden;
- `status.json`: voortgang en eventuele foutmelding;
- `landgebruik_met_code.csv`: de gebruikte codetabel.

Het logbestand is `productie.log` in dezelfde uitvoermap. Open het resultaat
in QGIS en controleer de dekking en klassen voor uw toepassing.

Bij nieuw berekende uitsneden en rastertegels wordt een `.qml`-bestand met
dezelfde bestandsnaam geschreven. Dit bevat de categorienamen uit de gebruikte
CSV, de landgebruikscodes en de binnen-/buitendijkse ligging. Bewaar TIFF en QML
bij elkaar. Voeg de TIFF opnieuw toe aan QGIS om de legenda te laden. Bij een
al geopende laag kunt u via **Laageigenschappen → Symbologie → Stijl → Stijl
laden** het QML-bestand kiezen. Bestaande uitvoer die wordt hergebruikt krijgt
niet automatisch een nieuwe stijl. Het landelijke startscript schrijft wel een
eigen QML-bestand bij het eindraster, ook als die TIFF wordt hergebruikt.

## NoData controleren

Voeg bij `bouw_functioneel_landgebruik_tiles(...)` of
`bouw_functioneel_landgebruik(...)` deze instelling toe:

```python
diagnostics_path=data_dir / "nodata.gpkg",
```

Open **nodata.gpkg** in QGIS. Het bestand bevat uitsluitend:

- laag **nodata**: vlakken die precies de lege cellen van het eindraster volgen;
- kolom **bron**: de betrokken bron, bijvoorbeeld BAG of BGT;
- kolom **reden**: een korte uitleg waarom hier geen landgebruik staat.

Gevulde rastercellen en afzonderlijke bronobjecten staan niet in deze laag.
Ook een punt zonder klasse verschijnt alleen als zijn rastercel leeg blijft.
Zonder NoData is de laag leeg.

Bij een open BAG-keuze staat de concrete reden, bijvoorbeeld meerdere
gebruiksdoelen of een ontbrekende oppervlakte. Bij andere gaten worden de
gevonden bronuitsluitingen vermeld, zoals uitgefilterde BGT-historie of een
ontbrekende CSV-koppeling. Meerdere aanwijzingen op dezelfde plek staan samen
in de reden. Dit bewijst niet dat een uitgesloten bronobject die plek in de
actuele situatie had moeten vullen. Zonder specifieke aanwijzing staat er:
**Geen bron vult deze plek.** De bron is dan **Niet vastgesteld**.
Als daar wel TOP10NL-terrein ligt, vermeldt de controle de bronwaarde, bijvoorbeeld:
**grasland aanwezig; TOP10NL-terreinlaag niet verwerkt.** De bron is dan **TOP10NL**.
Dit verklaart alleen het gat; het voegt geen landgebruiksklasse toe.

De controle verandert het raster niet. Grenzende vlakken kunnen gescheiden
blijven bij tegel- en verwerkingsgrenzen. De vlakoppervlakken overlappen niet
binnen de berekende tegel.

Workers schrijven tijdelijk onder `tiles/.nodata_controle/`. Pas na succesvol
samenvoegen verdwijnen deze losse bestanden: de uiteindelijke uitvoer is
alleen `nodata.gpkg`. Bij een fout blijven de tussenbestanden
beschikbaar voor hervatten. Een bestaand eindbestand kan bij hervatten de
controle voor ongewijzigde rastertegels leveren.

Zonder `diagnostics_path` wordt geen controle gemaakt. Bestaande rasters zonder
passende controle worden niet achteraf verklaard: bereken ze opnieuw met
`overwrite=True`. Het oudere controleformaat met objecten, punten en een
tegeloverzicht wordt niet als nieuwe NoData-controle hergebruikt. Voor hergebruik
worden rasterpad, bestandsgrootte en wijzigingsdatum gecontroleerd; deze
technische gegevens staan buiten de attributentabel.

## BAG controleren: brongegevens en statusselectie

Start vanuit de repository:

```powershell
pixi run python scripts/controle_bag_landgebruik.py
```

Het script maakt **één bestand** voor Flik-Flak en Vughterstraat:
`processed_data/functioneel_landgebruik/controle/bag_controle.gpkg`,
laag **bag_controle**. De kolom `uitsnede` geeft aan welk voorbeeld je bekijkt.
Vanaf stap 6 bevat hetzelfde bestand ook `gemalen_controle` als een gemalenbron
beschikbaar is. Dat is een puntlaag; de panden blijven in `bag_controle` staan.
Gebruik `identificatie` om een pand terug te vinden; QGIS-fid kan bij een nieuwe
uitvoer veranderen.

Lees eerst `toelichting_resultaat`: die vermeldt waarom het pand is ingedeeld,
uitgesloten of nog geen klasse heeft. Bij open functiecombinaties staan de
aantallen verblijfsobjecten en de niet-toepasbare regels concreet beschreven.
De grens van drie betreft verblijfsobjecten, niet het aantal verschillende functies.

Per pand staan alle stappen naast elkaar:

| Stap | Belangrijkste kolommen |
| --- | --- |
| 1. Bron | `status`, `gebruiksdoel`, `bron_aantal_vbo`, `bron_vbo_overzicht` |
| 2. Selectie | `meegenomen_stap2`, `reden_statusselectie` |
| 3. Functie | `gekozen_pandfunctie`, `functiekeuze_status`, `reden_functiekeuze` |
| 4. Bouwlagen | oppervlaktesom, pandoppervlakte, verhouding, bouwlagen en uitleg |
| 5. Klasse | omschrijving, beide codes, `klasse_status`, `reden_klasse` |
| 6. Bijzondere gebouwen | oorspronkelijke `basis_...`-klasse, bronkoppelingen, gemaalcapaciteit en uiteindelijke `reden_klasse` |

Het VBO-overzicht toont per verblijfsobject het ID, alle doelen en de gezamenlijke
oppervlakte. Het bronveld `gebruiksdoel` is niet de gekozen pandfunctie.
Uitgesloten panden blijven in de laag staan. Hun latere stappen zijn gemarkeerd
als niet uitgevoerd en krijgen geen klasse.

Standaard worden alle zes stappen uitgevoerd. Met `stap=5` bekijk je alleen
de gewone BAG-indeling. De losse berekeningsfuncties
blijven behouden, maar worden niet meer naar aparte bestanden of lagen geschreven.

Een enkelvoudig, overal gelijk gebruiksdoel wordt overgenomen. Bij maximaal
drie verblijfsobjecten met wonen en precies één niet-woon-verblijfsobject gaat
de andere functie voor, behalve overige gebruiksfunctie. Dit is de gekozen
afbakening van de wonen/andere-functie-regel. Bij minimaal twee niet-woon-
verblijfsobjecten met verschillende eenduidige doelen worden de oppervlakten
per niet-woonfunctie opgeteld en wordt het grootste totaal gekozen. Deze
optelling geldt ook bij meer dan drie VBO's. Wonen blijft buiten de
functieoppervlaktevergelijking, maar telt wel mee bij de bouwlagen. Dit is de
afgesproken interpretatie van de notitie; zie de
[functionele beschrijving](../bewerkingen/functioneel-landgebruik.md).
Meer dan drie VBO's met wonen en slechts één niet-woon-VBO blijven
`nog te beoordelen`.

Bij meerdere doelen in een verblijfsobject blijft de gekozen functie leeg,
met status `nog te beoordelen`. Hiervoor moeten we nog een beslisregel kiezen:
de gezamenlijke oppervlakte is niet per gebruiksdoel uitgesplitst.
Er wordt geen eerste doel gekozen of oppervlakte aan een doel toegewezen.

Gelijke grootste oppervlakten,
ongeldige benodigde oppervlakten en niet-opgeloste combinaties krijgen
`nog te beoordelen`. Bij een oppervlaktevergelijking geldt dit ook voor een
verblijfsobject dat aan meerdere panden is gekoppeld: de verdeling is onbekend.
Er wordt geen oppervlakte tussen panden verdeeld. Panden zonder
gekoppeld verblijfsobject krijgen `geen gebruiksdoel`, nog zonder klassecode.

Flik-Flak blijft daarom nog te beoordelen: onderwijs en sport delen een
verblijfsobject met 9.345 m². De bronwaarden blijven behouden.
Het winkel/woning-pand krijgt winkelfunctie ondanks het grotere
woonoppervlak. De BAG-voorbereiding gebruikt dezelfde indelingsfuncties als deze controle.


Stap 4 voegt de volgende kolommen toe aan dezelfde laag:

- `som_vbo_oppervlakte_m2`: som van alle gekoppelde VBO-oppervlakten;
- `pandoppervlakte_m2`: oppervlakte van de volledige pandgeometrie;
- `verhouding_vbo_pand`: VBO-som gedeeld door pandoppervlakte;
- `berekend_aantal_bouwlagen`: verhouding naar boven afgerond;
- `bouwlagen_status` en `reden_bouwlagen`: berekend of nog te beoordelen, met uitleg.

Dit volgt de berekening uit de notitie (p. 4-5). Ook woonoppervlakte telt mee
als de gekozen functie winkel is. Een VBO met meerdere doelen telt eenmaal
mee met zijn gezamenlijke oppervlakte. De functiekeuze uit stap 3 verandert
hierdoor niet: Flik-Flak kan berekende bouwlagen hebben en tegelijk nog een
openstaande functiekeuze. Het aantal bouwlagen is een schatting uit oppervlakten.

Zonder VBO, bij ontbrekende of ongeldige oppervlakten of bij een VBO dat aan
meerdere panden is gekoppeld, blijft de berekening open. Er wordt geen
oppervlakteverdeling aangenomen. Stap 4 kent nog geen woning/appartementklasse
of landgebruikscode toe. Controle en productie gebruiken dezelfde berekening.

Stap 5 voegt de volgende kolommen toe aan dezelfde laag:

- `lgb_omschrijving`: gebouwklasse op basis van functie en bouwlagen;
- `lgb_code_binnendijks` en `lgb_code_buitendijks`: beide mogelijke codes;
- `klasse_status` en `reden_klasse`: ingedeeld of nog te beoordelen, met uitleg.

De codes volgen tabel 1 uit de notitie van 17 september 2025 (p. 3-5).
Voor de tien reguliere functies gelden 1, 2 of 3-plus bouwlagen.
Een gekozen woonfunctie met maximaal 3 VBO's is een woning; vanaf 4 VBO's
een appartementencomplex (code 4/132), onafhankelijk van de bouwlagen.
Een openstaande functiekeuze blijft zonder klasse, ook als bouwlagen bekend zijn.
Flik-Flak blijft dus open. De winkel/woning krijgt met 4 berekende bouwlagen
de winkelklasse met 3 of meer bouwlagen (31/159).

Bij panden met uitsluitend overige gebruiksfunctie wordt de som van alle
gekoppelde VBO-oppervlakten gebruikt:
meer dan 100 m² geeft 32/160, maximaal 100 m² geeft 33/161.
Bij gemengde functies wordt eerst de leidende functie bepaald in stap 3.
Als overige gebruiksfunctie daarbij wint, staat de afbakening van de oppervlakte
voor de 100 m²-grens nog open. Ontbrekende oppervlakten worden niet als nul
meegeteld. Geen gebruiksdoel in stap 3 geeft de
aparte categorie 34/162, niet dezelfde categorie als een onopgeloste combinatie.

Deze stap bepaalt nog geen binnen-/buitendijkse ligging. Er wordt geen
definitieve rastercode gekozen. TOP10NL-aanvullingen zoals kassen zijn hier
nog niet toegepast. Stap 5 leest codes en omschrijvingen uit de CSV;
`lgb_koppeling_id` laat zien welke rij is gebruikt. De landelijke verwerking
gebruikt dezelfde tabel en BAG-beslisregels.

### Stap 6 controleren

De TOP10NL-GeoPackage moet `top10nl_gebouw_vlak` bevatten. Kassen worden daarin
automatisch opgezocht. De standaardvoorbeelden hoeven geen kas of gemaal te
bevatten; kies daarvoor een passende `bounds`.

In `gemalen_controle` staan de broncapaciteit, beide mogelijke codes,
`bag_pand_id`, `bag_gebruiksdoelen`, `geometrie_kaart`,
`pand_capaciteit_m3_min` en `reden_ruimtelijke_koppeling`. De puntlaag behoudt
alle bronpunten, ook als voor de kaart een BAG-pand wordt gebruikt of geen
capaciteitsklasse kon worden bepaald. Bekijk in `bag_controle` de kolommen
`gekoppelde_gemalen` en `gemaalcapaciteit_m3_min` voor de panduitkomst.

Een pand zonder gekoppeld VBO of met uitsluitend lege gebruiksdoelen mag nu
ook worden gekoppeld. De gemaalbron levert het bewijs van de gemaalfunctie.
Het punt moet binnen precies één geselecteerd pand liggen en de gezamenlijke
capaciteit moet geldig en indeelbaar zijn. De controle vermeldt waarom het
pand is gebruikt. Een combinatie van een bekend doel en een ontbrekend doel
wordt niet automatisch gekoppeld.

Aanvullende bronnen zijn optioneel en worden niet automatisch gedownload.
Voor het controlescript geef je `special_sources=SpecialBuildingSources(...)`
op, uit `waterlagen.functioneel_landgebruik.kassen_rwzi_drinkwater`. Naast
`top10nl_gpkg` kun je `rwzi_gpkg`, `rwzi_layer`, `rwzi_status_column`,
`rwzi_active_value`, `drinking_water_gpkg` en `drinking_water_layer` instellen.
Gebruik alleen een statuswaarde waarvan vaststaat dat deze operationeel
gebruik aangeeft. Met `gemalen_gpkg` kun je een eigen HyDAMO-bestand aanwijzen.

Voor rasterproductie staan de optionele paden op `FunctioneelLandgebruikSources`
(`rwzi_gpkg`, `drinking_water_gpkg`, `gemalen_gpkg`) en de bijbehorende laag- en
veldnamen op `FunctioneelLandgebruikLayers`. Gebruik `dataclasses.replace` om
de paden van `FunctioneelLandgebruikSources.from_datastore(...)` aan te vullen.
Controleer de [selectieregels en beperkingen](../bewerkingen/functioneel-landgebruik.md#bijzondere-gebouwen-en-gemalen-stap-6)
voordat je de uitkomsten gebruikt.

### Meerdere gemalen in één pand controleren

Voer `pixi run python scripts/controle_gemalen_landgebruik.py` uit voor een
uitsnede van 500 × 500 meter rond gemaal Lely. De huidige bron bevat drie
afzonderlijke gemaalobjecten (afdelingen 2, 3 en 4) van elk 450 m³/min, binnen
BAG-pand `0463100000001005` met overige gebruiksfunctie. De verwachte som is
1.350 m³/min: klasse >1.000, codes 43/171. Dit controleert de verwerking van de
bronregistraties; het bewijst niet onafhankelijk de werkelijke pompcapaciteit.

De uitvoer staat onder `processed_data/functioneel_landgebruik/controle_gemalen_lely`:

- `controle.gpkg`: lagen `bag_controle` en `gemalen_controle`;
- `landgebruik.tif` en `landgebruik.qml`: raster met categorielegenda;
- `berekening.log`: voortgang.

Controleer bij het pand `gekoppelde_gemalen`, `gemaalcapaciteit_m3_min` en
beide `lgb_code`-kolommen. Bij de punten staan de afzonderlijke capaciteiten,
`bag_pand_id`, `geometrie_kaart` en `pand_capaciteit_m3_min`.
Het script hergebruikt de lokale bronnen en overschrijft alleen dit voorbeeld.
Sluit de uitvoer in QGIS voor opnieuw draaien. Pas zo nodig `BGT_FILENAME`
aan; standaard wordt het herstelde `bgt.gpkg` gebruikt.

### De codetabel aanpassen

De standaardtabel staat in
`src/waterlagen/functioneel_landgebruik/landgebruik_met_code.csv`.
Deze CSV is onderdeel van de codeversie. De documentatiemap kan een kopie
bevatten; wijzigingen daarin worden niet automatisch naar de pakketversie
gekopieerd. Geef het betreffende pad expliciet op om die kopie te gebruiken.

Beide startscripts hebben bovenin `LANDGEBRUIK_CSV`. Stel daar desgewenst een
eigen `Path(...)` in. Het productiescript bewaart de gebruikte CSV in de uitvoermap.
Vanuit Python kan dit ook met `main(mapping_csv=Path(...))` of met
`bouw_functioneel_landgebruik(..., mapping_csv=Path(...))`.

Gebruik puntkomma's als scheidingsteken en behoud de kolomnamen en vaste
koppeling-ID's. Rijen mogen worden verplaatst; hun positie bepaalt de klasse
niet. Onjuiste codes, ontbrekende BAG-koppelingen en dubbele ID's geven een
foutmelding. `landgebruik_zonder_code.csv` is een overzicht voor beoordeling
en wordt niet als codetabel ingelezen.

Bestaande rasters worden bij `overwrite=False` hergebruikt en veranderen niet
mee met de CSV. Gebruik voor een nieuwe codering een nieuwe uitvoermap, of
bereken de betrokken tegels en het eindraster opnieuw met `overwrite=True`.
De BAG-controle vernieuwt bij rechtstreeks starten wel het controlebestand.

De BGT-GeoPackage moet nu ook `bgt_begroeidterreindeel`,
`bgt_onbegroeidterreindeel` en `bgt_ondersteunendwegdeel` bevatten, naast
waterdelen en wegdelen, steeds met de einddatumvelden. Een bestaand onvolledig
bronbestand wordt niet automatisch opnieuw gedownload.

Voor TOP10NL zijn zowel `top10nl_functioneel_gebied_vlak` als
`top10nl_functioneel_gebied_multivlak` nodig voor de terreinindeling. Beide
zitten in het volledige TOP10NL-bestand. Een ontbrekende laag geeft een
foutmelding; deze wordt niet stilzwijgend overgeslagen.


De uitsnede selecteert panden. Verblijfsobjecten worden daarna via de exacte
pand-ID-koppeling opgehaald, ook buiten de uitsnede. Geometrie en bronwaarden
blijven intact. Een verblijfsobject kan aan meerdere panden gekoppeld zijn;
zijn volledige bronoppervlakte blijft bij dat object staan en wordt niet over
panden verdeeld. Een pand zonder koppeling blijft eveneens zichtbaar.

Pas `BOUNDS` en `WINKEL_WONING_BOUNDS` bovenin het script aan voor andere
uitsnedes. Uitvoeren via het script vernieuwt het gezamenlijke controlebestand.
Sluit de laag in QGIS als het bestand daardoor vergrendeld is.
Bij rechtstreeks aanroepen van `main()` wordt een bestaand bestand hergebruikt;
gebruik `main(overwrite=True)` om het te vernieuwen.

Een vooraf voorbereid BGT-bestand kan aan `main(bgt_path=...)` in het
startscript worden doorgegeven. Deze route downloadt of converteert geen BGT.
Aanvullende vlaklagen in dat bestand worden gebruikt om NoData te verklaren.
