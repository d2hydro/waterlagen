# Functioneel landgebruik

## Doel

Deze bewerking maakt een geclassificeerd raster voor functioneel landgebruik.

## Bronnen

- [TOP10NL](../bronnen/top10nl.md)
- [BRP](../bronnen/brp.md)
- [BGT](../bronnen/bgt.md)
- [BAG](../bronnen/bag.md)
- [LIWO](../bronnen/liwo.md)
- [GKW HYDAMO](../bronnen/hydamo.md) voor gemaalpunten en capaciteit
- [Waterketen DAMO](../bronnen/waterketen-damo.md) voor bevestiging van RWZI-terreinen

## Werkwijze

Waterlagen leest de benodigde vectorlagen binnen het gevraagde gebied,
classificeert bronattributen naar de functionele-landgebruiklegenda en
rasteriseert de lagen in een vaste prioriteitsvolgorde. TOP10NL, BRP, BGT
en BAG-klassen worden onderscheiden naar binnen- en buitendijks op basis van
hun representatieve punt en uitsluitend de LIWO-selectie
`source_data/liwo/buitendijks_gebied_uit_liwo.gpkg`. Een punt binnen of op de
grens van deze polygonen (`covered_by`) is buitendijks; alle overige punten
zijn binnendijks. Alleen overlap van een object met een polygoon is dus niet
voldoende. Objecten worden niet op de grens opgeknipt. Dijkringen worden
hiervoor niet gebruikt. Zie [LIWO-selectie](liwo-selectie.md).

Bronnen, tegelrooster en uitvoer moeten hetzelfde project-CRS gebruiken
(`settings.crs`, standaard `EPSG:28992`). Bij een afwijking stopt de verwerking;
de bronnen worden niet automatisch geherprojecteerd.

Voor BAG-panden worden uitsluitend de statussen `Bouw gestart`, `Pand in gebruik`
en `Verbouwing pand` meegenomen, volgens pagina 4 van de landgebruiknotitie
van 17 september 2025. Andere of ontbrekende statussen worden uitgesloten,
ook `Pand in gebruik (niet ingemeten)`. Deze selectie geldt eveneens voor
panden zonder gekoppeld verblijfsobject. Een ontbrekende statuskolom geeft een
foutmelding.

### Beslisboom voor de gebouwfunctie

De onderstaande beslisboom beschrijft de classificatie per pand.
Een VBO is een verblijfsobject; `NULL` betekent een ontbrekende gebruiksfunctie.
De diagramterm `overigegebruiksfunctie` komt overeen met
`overige gebruiksfunctie` in de code en de overige documentatie.

Vooraf wordt per VBO één gebruiksfunctie gekozen. Bij meerdere, door komma's
gescheiden doelen geldt deze prioriteit, van hoog naar laag:

1. `gezondheidszorgfunctie`
2. `winkelfunctie`
3. `kantoorfunctie`
4. `industriefunctie`
5. `woonfunctie`
6. `logiesfunctie`
7. `onderwijsfunctie`
8. `sportfunctie`
9. `bijeenkomstfunctie`
10. `celfunctie`
11. `overige gebruiksfunctie`

Hoofdletters, omliggende spaties, dubbele doelen en lege onderdelen beïnvloeden
de keuze niet. Een onbekend doel laat de pandkeuze open, ook naast bekende doelen.
Uitsluitend lege doelen blijven `NULL`. Het volledige VBO-oppervlak wordt voor
de classificatie eenmaal aan de gekozen functie toegerekend; dit is geen gemeten
verdeling van het vloeroppervlak. De oorspronkelijke doelen blijven bewaard,
ook voor controles zoals de koppeling van gemalen. De prioriteitskeuze wordt
toegelicht in de diagnostiek.

De beslisboom hieronder gebruikt deze geselecteerde VBO-functies, ook voor
de aanwezigheid van wonen en het aantal niet-woon-VBO's. Zo wordt
`woonfunctie,winkelfunctie` één niet-woon-VBO met winkelfunctie.
Eerst wordt onderscheid gemaakt tussen panden met en zonder geselecteerde `woonfunctie`.
Zonder woonfunctie wordt het vloeroppervlak per gebruiksfunctie opgeteld.
Eén functie wordt direct gekozen; bij meerdere functies met uitsluitend
`overigegebruiksfunctie` en `NULL` wordt `overigegebruiksfunctie` gekozen.
In alle andere gevallen worden de functies op aflopend totaal vloeroppervlak
doorlopen: sla `NULL` en `overigegebruiksfunctie` met een totaal kleiner dan
100 m² over en kies de eerste resterende functie. Precies 100 m² wordt dus
niet overgeslagen. Deze uitsluitingsregel geldt alleen bij de rangschikking,
niet bij de directe keuze van één functie of de combinatie overige en `NULL`.

Met woonfunctie bepaalt eerst het totale aantal VBO's de tak. Bij maximaal
drie VBO's geeft nul niet-woon-VBO's een woning; bij precies één bepaalt die
andere functie de keuze, behalve bij overige of `NULL`, die ook een woning
opleveren. Vanaf vier VBO's geven nul of één niet-woon-VBO een
appartementencomplex. Bij minstens twee niet-woon-VBO's geldt in beide takken
dezelfde sommeer-, uitsluitings- en rangschikkingslogica als zonder woonfunctie,
maar uitsluitend voor de niet-woonfuncties.

[![Beslisboom voor de gebouwfunctie op basis van BAG-verblijfsobjecten](../images/beslisboom_bag_vbo.svg)](../images/beslisboom_bag_vbo.svg)

### Huidige uitvoering van de gebouwclassificatie

De BAG-voorbereiding gebruikt dezelfde functiekeuze, bouwlagenberekening en
gebouwklassen als het controlescript en volgt de beslisboom hierboven.
Onbekende doelen binnen een VBO blijven open. De prioriteit binnen een VBO
is geen voorrangsregel tussen verschillende VBO's. Bij rangschikking
blijven gelijke grootste totalen na uitsluiting open: de beslisboom geeft
geen voorrang bij gelijke oppervlakten. Ontbrekende, ongeldige of over meerdere
panden gedeelde oppervlakten blijven open wanneer ze nodig zijn voor de
vergelijking. De oppervlakte van `NULL` is daarvoor niet nodig. Bij directe
functiekeuzes wordt geen oppervlaktevergelijking uitgevoerd.
Uitsluitend `NULL` onder de kandidaatfuncties geeft `geen gebruiksdoel`,
evenals een pand zonder gekoppelde VBO's.
De code stelt niet vast op welke verdieping een functie werkelijk zit.
Bouwlagen volgen uit alle gekoppelde VBO-oppervlakten gedeeld door de volledige
pandoppervlakte, naar boven afgerond. Vanaf vier VBO's krijgt een gekozen
woonfunctie de appartementklasse. De gebouwcodes volgen tabel 1 van de notitie.

Bij panden met uitsluitend `overige gebruiksfunctie` wordt de som van alle
gekoppelde VBO-oppervlakten vergeleken met 100 m²: maximaal 100 m² geeft
33/161, meer dan 100 m² geeft 32/160. Dit is de afgesproken uitwerking voor
meerdere VBO's in één pand. Een ontbrekende of ongeldige oppervlakte wordt
niet als nul meegeteld; de klasse blijft dan open. Bij gemengde functies wordt
eerst de leidende functie bepaald. Als dat overige gebruiksfunctie is, staat
de oppervlakteafbakening voor de 100 m²-grens nog open.

VBO's worden via hun pand-ID gekoppeld, ook als hun punt buiten de tegel ligt.
Een openstaande klasse krijgt rastercode 0 (NoData); de gebouwgeometrie wist
daarmee een eventueel eerder gerasterde terreinfunctie op die plek.
Met `prepare_bag(..., include_details=True)` blijven de redenen zichtbaar.

## Codes uit de CSV

De codes en omschrijvingen komen uit
`src/waterlagen/functioneel_landgebruik/landgebruik_met_code.csv`.
De tabel is gebaseerd op de notitie van 17 september 2025 en wordt met het
pakket meegeleverd. Een eigen tabel kan via `mapping_csv` worden opgegeven.
De kolommen `LGB-code_binnendijks` en `LGB-code_buitendijks` bevatten gehele
getallen van 1 t/m 255; code 0 is gereserveerd voor NoData. `LGB_beschrijving`
levert de klassenaam. `Toelichting` en `Documentatie` beïnvloeden de indeling niet.
De tabel onderscheidt directe bronwaardekoppelingen (`mapping`) en vaste
Python-regels (`functie`, geïdentificeerd door `Koppel-ID`). Elke nieuwe tabelrij
bevat één bronwaarde. Zie [de codetabel aanpassen](../produceren/landgebruik.md#de-codetabel-aanpassen)
voor het bestandsformaat en de bewerkbare kolommen.

Een expliciete waarde gaat voor het vangnet `*`. Met een bronveld vangt dit
alleen geldige, niet-lege waarden op; BRP vereist positieve gehele gewascodes.
Zonder bronveld geldt de regel voor alle verder geschikte objecten. Die variant
wordt gebruikt voor BGT-water en onbegroeide terreindelen. Ontbrekende of lege
attribuutwaarden krijgen bij een veldgebonden koppeling geen klasse uit die laag.

De CSV-volgorde bepaalt noch de classificatie, noch de presentatie. Als meerdere
bronnen dezelfde code gebruiken, is de kleurvoorrang: BGT-water, gebouwen,
BRP, TOP10NL, BGT-wegen en overige terreinen/gemalen. Dit is uitsluitend een
kleurkeuze, geen rastervoorrang. Voor een gedeelde buitencode krijgt de
beschrijving van de rij met `buitencode = binnencode + 128` voorrang. Ontbreekt
zo'n rij, dan worden de verschillende beschrijvingen alfabetisch samengevoegd.
Die voorkeur bepaalt alleen het legendalabel, niet de uitvoercode.

- **BAG:** de functiekeuze en berekening van bouwlagen blijven afzonderlijke
  stappen. De uitkomst kiest een vaste koppeling-ID; de CSV levert daarna de
  omschrijving en beide codes. Er wordt geen code berekend met een vaste offset.
  Koppeling-ID's blijven bij dezelfde betekenis horen wanneer je rijen sorteert
  of toevoegt. De verwerking stopt als een vereiste BAG-ID naar een andere bron
  of gebruiksfunctie verwijst. Bouwlagen en de aparte gebouwregels blijven in
  Python vastgelegd; daarvoor zijn geen extra CSV-kolommen nodig. Het verwisselen
  van twee bouwlagenklassen binnen dezelfde functie wordt niet door deze
  functiecontrole herkend.
- **BRP:** koppeling op `gewascode`, inclusief de in de CSV opgenomen
  landschapselementen. Gewascodes 265 en 266 krijgen 50 binnendijks en 182
  buitendijks, volgens de uitzondering op pagina 9. De overige codes uit
  tabelrij 50/178 houden 50/178. Overige geldige gewascodes gebruiken alleen
  het expliciete CSV-vangnet 53/181; het gebruik hiervan wordt gelogd.
- **BGT:** wegen, ondersteunende wegdelen en begroeide terreindelen worden op
  volledige bronwaarden gekoppeld. De CSV bevat ook een algemene regel voor
  onbegroeide terreindelen en waterdelen. De afbakening van onbegroeide
  terreindelen als erf is nog een inhoudelijk aandachtspunt.
- **TOP10NL:** volledige bronwaarden van functionele gebieden worden gekoppeld.
  Zowel `top10nl_functioneel_gebied_vlak` als
  `top10nl_functioneel_gebied_multivlak` wordt verwerkt met de koppelingen uit
  de CSV. Een multivlak behoudt zijn afzonderlijke terreindelen en krijgt op
  dezelfde manier een binnen- of buitendijkse code. Beide lagen liggen op
  dezelfde positie ten opzichte van de overige bronnen in de rastervolgorde.
  Dit is een technische aanvulling op tabel 6 van de notitie, die alleen
  `vlak` noemt; er worden geen extra landgebruikscategorieën toegevoegd.
  `zonnepark` wordt daardoor niet via het woord `park` geclassificeerd.
  Bronwaarden zonder koppeling worden gelogd en niet ingetekend.

### Overlap en rastervoorrang

Bij `mapping` krijgt een bronobject maximaal één koppeling: een expliciete
bronwaarde gaat voor `*`. Dubbele bronwaarden binnen dezelfde bronlaag geven
een foutmelding. Een object zonder koppeling wordt niet ingetekend en wist dus
geen eerder ingetekende klasse.

Verschillende bronobjecten kunnen wel dezelfde rastercel raken. Alle door een
geometrie geraakte cellen worden ingetekend (`all_touched=True`), waardoor ook
aangrenzende vlakken een cel kunnen delen. Voor zowel `mapping` als `functie`
geldt deze tekenvolgorde; een latere laag overschrijft een eerdere laag:

1. BGT-begroeide terreindelen, daarna onbegroeide terreindelen.
2. TOP10NL-functionele gebieden: eerst `vlak`, daarna `multivlak`.
3. BRP.
4. BGT-ondersteunende wegdelen.
5. BGT-wegdelen.
6. BAG-panden met hun uiteindelijke gebouwklasse.
7. Gemalen die als punt zijn behouden.
8. BGT-waterdelen.

Een BGT-weg die dezelfde cel raakt als BRP-gras overschrijft dus de grascode.
Water gaat vervolgens voor wegen, gebouwen en landbouw en krijgt de binnen- of
buitendijkse CSV-code (standaard 100/228). De overige volgorde is het huidige
gedrag van de verwerking; hiermee zijn niet alle inhoudelijke vragen over
overlap opgelost.

Binnen één laag wint het laatst ingetekende object in de aangeleverde
objectvolgorde. Er is geen algemene conflictcontrole of keuze op basis van
grootste oppervlak. Bij overlappende objecten kan een gewijzigde bronvolgorde
dus een ander raster opleveren. De volgorde van de CSV-rijen en de hoogte van
de LGB-codes bepalen deze voorrang niet. De kleurvoorrang in de legenda staat
hier eveneens los van.

Voor `functie` wordt eerst de gebouwklasse bepaald. De gewone BAG-regels
kiezen één uitkomst; onopgeloste functiekeuzes blijven open. Bijzondere
gebouwregels hebben daarnaast de conflictcontrole hieronder. Een onopgelost
gebouw krijgt code 0 (NoData): de gebouwgeometrie wist daarmee eerder
ingetekende terreinklassen. Later ingetekende gemaalpunten of water kunnen
die cellen alsnog overschrijven.

### Bijzondere gebouwen en gemalen (stap 6)

Na de gewone BAG-indeling worden de volgende aanvullingen toegepast. De codes
komen uit dezelfde CSV. De controle bewaart de oorspronkelijke BAG-uitkomst
in `basis_...`-kolommen, naast de uiteindelijke klasse en reden.

| Onderwerp | Selectie en resultaat |
| --- | --- |
| Kassen | TOP10NL-gebouwtype `kas, warenhuis`, ook als afzonderlijke waarde in een combinatie met `\|`. Als deze geometrie meer dan de helft van een BAG-pand bedekt, krijgt dat pand de kassenklasse. De BAG-geometrie blijft behouden. |
| RWZI | Polygonen uit `top10nl_functioneel_gebied_vlak` met exact `typefunctioneelgebied == "zuiveringsinstallatie"`, die een object uit Waterketen DAMO-laag `rwzi` snijden. BAG-panden met hun representatieve punt strikt binnen zo'n terrein krijgen `RWZI (gebouw op RWZI-terrein)`, codes 36/164. Er geldt geen statusfilter. |
| Drinkwater | BAG-panden waarvan het representatieve punt binnen een aangeleverd drinkwaterproductieterrein ligt krijgen de drinkwaterklasse. |
| Gemalen | Capaciteit in m³/min bepaalt de klasse. Gebruik een BAG-pand als het gemaalpunt binnen precies één geselecteerd pand ligt en het pand uitsluitend industrie-/overige gebruiksfunctie heeft, geen gekoppeld VBO heeft, of uitsluitend lege gebruiksdoelen heeft. Wonen, andere bekende functies, onbekende bronwaarden en deels ontbrekende doelen sluiten automatische pandkoppeling uit; het gemaal blijft dan een punt. |

De ruimtelijke grenzen voor deze koppelingen zijn uitvoeringskeuzes; de notitie
schrijft geen overlappercentage of exacte koppelprocedure voor. Ook een kleine
woonfunctie binnen een verder industrieel pand blokkeert automatische koppeling
van een gemaal aan het gehele pand. Deels ontbrekende gebruiksdoelen en andere functies
blijven eveneens als punt ter beoordeling. Er wordt geen dichtstbijzijnd pand gekozen.

Voor RWZI wordt het volledige TOP10NL-terrein gebruikt: het bevestigende DAMO-object
mag buiten de verwerkte tegel of pandbegrenzing liggen. Een DAMO-object op de
terreinrand bevestigt het terrein door `intersects`. Alleen raken van een terrein
door een BAG-pand is onvoldoende; ook een representatief pandpunt op de rand
wordt uitgesloten. De laag `top10nl_functioneel_gebied_multivlak` doet niet mee
aan deze gebouwregel. De vaste koppeling-ID blijft `TOP10NL-NGR-BAG-001` voor
compatibiliteit met bestaande codetabellen; de bron is nu DAMO. Eigen codetabellen
blijven de codes en omschrijving bepalen.

Bij meerdere afzonderlijke gemalen in hetzelfde geschikte pand worden de
capaciteiten opgeteld. Dezelfde `globalid` telt eenmaal; tegenstrijdige capaciteiten
bij dezelfde ID, ontbrekende capaciteiten of ontbrekende IDs bij meerdere gemalen
verhinderen een automatische som. De puntrecords blijven dan zichtbaar. Er worden
geen pomp-records bij gemaalcapaciteiten opgeteld.

#### Conflicten tussen bijzondere gebouwregels

Een passende kas-, RWZI- of drinkwaterregel vervangt de gewone BAG-klasse.
Als meerdere van deze regels bij hetzelfde pand passen, zijn ze alleen
verenigbaar als hun volledige codeparen
(`LGB-code_binnendijks`, `LGB-code_buitendijks`) gelijk zijn. Beide codes
moeten overeenkomen, ook als het pand uitsluitend binnendijks ligt. Bij gelijke
paren wordt dat paar gebruikt; de vaste verwerkingsvolgorde van de regels
bepaalt de gerapporteerde `Koppel-ID`, terwijl alle passende IDs in de controle
bewaard blijven. De CSV-volgorde bepaalt deze keuze niet.

Bij verschillende codeparen blijft het pand `nog te beoordelen`, zonder
definitieve klasse. De verwerking valt dan niet terug op de gewone BAG-klasse;
het pand wordt als NoData ingetekend volgens de
[rastervoorrang](#overlap-en-rastervoorrang).

Bijvoorbeeld: een pand past zowel bij de kasregel met codes `(35, 163)` als bij
de RWZI-regel met `(36, 164)`. Dit levert een conflict op. Als beide regels in
de CSV hetzelfde paar `(35, 163)` krijgen, is hun uitkomst verenigbaar. Alleen
de binnencodes gelijk maken is onvoldoende. Het aanpassen van codes kan dus
ook veranderen of een pand een definitieve klasse krijgt.

Voor een aan een pand gekoppeld gemaal geldt een strengere regel. Een geldige
gemaalklasse kan de gewone BAG-klasse vervangen, maar een gelijktijdige kas-,
RWZI- of drinkwaterkoppeling maakt het pand onopgelost, **ook bij gelijke
codeparen**. Er is geen automatische voorrang tussen het gemaal en die
bijzondere gebouwfuncties. Een ruimtelijk onduidelijke gemaalkoppeling kiest
geen pand; het gemaal blijft dan een punt.

De zes capaciteitsintervallen zijn **10 ≤ Q < 20**, **20 ≤ Q < 50**,
**50 ≤ Q < 100**, **100 ≤ Q < 400**, **400 ≤ Q ≤ 1000** en **Q > 1000**.
Dit gebruikt alle zes tabelklassen vanaf 10, volgens de projectkeuze; het
50-criterium uit de lopende tekst wordt niet gebruikt. Een pandtotaal wordt
berekend vóór toepassing van de klassegrenzen. Ontbrekende, negatieve of
ongeldige capaciteiten krijgen geen klasse.

Een overgebleven gemaalpunt beslaat één rastercel, zonder verondersteld
gebouwoppervlak. Die punten worden na BAG en vóór BGT-water gerasterd. Water
houdt dus de bestaande voorrang. Het puntenbestand blijft nodig voor controle:
een punt op water kan in het samengestelde raster door water worden overschreven,
en meerdere punten kunnen in dezelfde rastercel vallen.

Kassen worden standaard gecontroleerd. Een aanwezige `hydamo/hydamo.gpkg`
wordt bij gebruik van de datastore meegenomen voor gemalen. Een aanwezige
`waterketen_damo/waterketen_damo.gpkg` wordt gebruikt voor RWZI-terreinen.
Drinkwaterproductieterreinen moeten afzonderlijk worden ingesteld.
Zonder die bronnen worden de betreffende selecties overgeslagen en gelogd;
de gewone BAG-klasse blijft staan. `Gerealiseerd` geldt niet automatisch als
`in gebruik`. De status van gemaalobjecten blijft in de controle zichtbaar;
de capaciteitsindeling op zichzelf bevestigt niet dat een gemaal operationeel is.

Alle gebruikte BGT-lagen worden alleen verwerkt als de status `bestaand` is
en zowel `eindRegistratie` als `objectEindTijd` leeg (NULL) zijn. Status alleen
is onvoldoende: ook historische registraties kunnen `bestaand` vermelden.
De selectie gebeurt per registratie; een beëindigde versie sluit een actuele
versie van hetzelfde object niet uit. Ontbreken de benodigde kolommen, dan
stopt de verwerking met een foutmelding. Maak dan de BGT-GeoPackage opnieuw
met de einddatumvelden. Bestaande rasters worden hiermee niet automatisch
opnieuw berekend.

Bij het omzetten van BGT-wegdelen en terreindelen naar GeoPackage gebruikt
Waterlagen het vlak uit `geometrie2d`. Een aanwezige `kruinlijn` mag dit vlak
niet vervangen. Anders kan een actuele registratie als lijn worden opgeslagen
en ontstaat na het verwijderen van de historische versie onterecht NoData.
Oudere GeoPackages met dit probleem moeten opnieuw uit de GML worden gemaakt;
daarna moeten ook de betreffende rastertegels opnieuw worden berekend.

## Uitvoer

De uitvoer is een gepaletteerde GeoTIFF met één `uint8`-band `Landgebruik`,
NoData-waarde 0 en overviews. De standaardresolutie is 0,5 m en de standaard-CRS
is `EPSG:28992`.

Optioneel wordt één GeoPackage-laag met uitsluitend de NoData-vlakken
geschreven. De kolommen `bron` en `reden` geven de bron en de open keuze of aangetroffen uitsluiting.
Aanwezige aanvullende BGT-vlaklagen worden ook gecontroleerd op actuele objecten.
Bijvoorbeeld: bron `BGT`, reden `Oever/slootkant: geen landgebruikscode.`
Deze aanwijzing gaat voor historische registraties en TOP10NL-terrein.
Een concrete BAG-keuze die NoData veroorzaakt blijft behouden. Dit verandert
alleen de uitleg, niet de landgebruikscode. Lagen die niet in het BGT-GeoPackage
staan zijn niet gecontroleerd; hun afwezigheid bewijst niet dat de ruwe BGT leeg is.
Zonder specifieke aanwijzing staat er dat de gebruikte bronnen geen landgebruik
hebben toegekend. De vlakken volgen exact de lege rastercellen. Zie
[NoData controleren](../produceren/landgebruik.md#nodata-controleren)
voor het inschakelen en bekijken in QGIS.

## Aandachtspunten en beperkingen

De classificatie volgt de in Waterlagen vastgelegde legenda en de beschikbare
bronattributen. Het raster is daarom een afgeleid product, geen vervanging van
een afzonderlijke bronregistratie. Ontbrekende bronbestanden kunnen desgewenst
vooraf door de workflow worden gedownload.

## Zelf produceren

Volg [Functioneel landgebruik produceren](../produceren/landgebruik.md) voor
de workflow met het productiepakket. Voor eigen Python-workflows gebruikt u
`bouw_functioneel_landgebruik`; zie de [API-referentie](../reference/functioneel_landgebruik.md).
