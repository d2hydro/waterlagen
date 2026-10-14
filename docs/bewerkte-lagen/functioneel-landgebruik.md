---
editorial_status: human
---

# Functioneel landgebruik

## Doel

Deze bewerking combineert gebouwen, terreinen, wegen en water tot één landgebruikraster. Iedere cel krijgt een landgebruiksklasse, met een aparte code voor buitendijkse ligging.

## Bronlagen

| Bron | Gebruik |
| --- | --- |
| [BAG](../bronlagen/bag.md) | Panden, verblijfsobjecten (VBO's), gebruiksdoelen en oppervlakten. |
| [BGT](../bronlagen/bgt.md) | Wegen, terreinen, oevers en water. |
| [BRP](../bronlagen/brp.md) | Gewaspercelen en landschapselementen. |
| [TOP10NL](../bronlagen/top10nl.md) | Functionele gebieden, landbouwterreinen en kassen. |
| [GKW HYDAMO](../bronlagen/hydamo.md) | Gemaalpunten en capaciteit. |
| [Waterketen DAMO](../bronlagen/waterketen-damo.md) | Bevestiging van RWZI-terreinen. |
| [OSM-drinkwaterlocaties](../bronlagen/osm-drinkwater.md) | Beoordeelde drinkwaterproductieterreinen. |
| [LIWO](../bronlagen/liwo.md) | Afbakening voor de buitendijkse codering. |
| [Bestuurlijke gebieden](../bronlagen/bestuurlijke-gebieden.md) | Begrenzing voor het aanvullen van gaten en de NoData-controle. |

## Werkwijze

Het gekozen gebied wordt verdeeld in tegels. Per tegel worden vier stappen uitgevoerd:

1. Landgebruiksklassen bepalen voor gebouwen, terreinen, wegen en water
2. Buitendijkse codes toekennen.
3. Bronnen in een vaste volgorde intekenen.
4. Gaten aanvullen en controleren.

De tegels krijgen een overlap voor berekeningen langs de randen. Daarna worden ze teruggesneden en samengevoegd tot één raster.

### 1. Landgebruiksklassen bepalen voor gebouwen, terreinen, wegen en water

#### Gebouwen selecteren

Alleen BAG-panden met deze statussen worden meegenomen:

- `Bouw gestart`;
- `Pand in gebruik`;
- `Verbouwing pand`.

Andere of ontbrekende statussen vallen af. Ook `Pand in gebruik (niet ingemeten)` valt af.

Een verblijfsobject (VBO) is bijvoorbeeld een woning of winkel binnen een pand. Alle VBO's die volgens de BAG bij het pand horen, tellen mee.

<a id="beslisboom-voor-de-gebouwfunctie"></a>

#### Gebouwfunctie kiezen

Per VBO wordt eerst één gebruiksfunctie gekozen. Bij meerdere doelen geldt deze volgorde, van hoog naar laag:

'Gezondheidszorg → winkel → kantoor → industrie → wonen → logies → onderwijs → sport → bijeenkomst → cel → overige gebruiksfunctie.'

Bij gecombineerd gebruik telt het hele VBO-oppervlak mee bij de functie met de hoogste prioriteit.

[![Beslisboom voor de gebouwfunctie op basis van BAG-verblijfsobjecten](../images/beslisboom_bag_vbo.svg)](../images/beslisboom_bag_vbo.svg)

Aanvullend op de beslisboom:

- `NULL` betekent een leeg gebruiksdoel. Geen VBO's of uitsluitend `NULL` bij de kandidaatfuncties geeft *geen gebruiksdoel*.
- Bij een ingevuld maar niet-herkend gebruiksdoel is de pandfunctie niet te bepalen.
- Bij gelijke grootste totale oppervlakten geldt de prioriteitsvolgorde hierboven.
- Ontbrekende, ongeldige of over meerdere panden gedeelde oppervlakten worden niet geschat. Als de keuze deze gegevens nodig heeft, blijft die open.

<a id="bouwlagen-en-gebouwklasse-bepalen"></a>

#### Gebouwklasse bepalen

Het aantal bouwlagen wordt geschat: 'som van alle VBO-oppervlakten / volledige pandoppervlakte', naar boven afgerond. Woonoppervlakte telt hierbij wel mee.

| Uitkomst | Gebouwklasse |
| --- | --- |
| Reguliere functie | Klasse voor 1, 2 of 3 of meer bouwlagen. |
| Woonfunctie met minimaal 4 VBO's | Appartementencomplex, ongeacht de bouwlagen. Codes 4/132. |
| Overige gebruiksfunctie | Alleen de oppervlakte van VBO's met die gekozen functie telt. Maximaal 100 m²: 33/161. Meer dan 100 m²: 32/160. |
| Geen gebruiksdoel | Aparte klasse, codes 34/162. |
| Onopgeloste functiekeuze of ontbrekende benodigde oppervlakte | Geen klasse: NoData. |

De codeparen noemen steeds de standaardcode en de buitendijkse code uit de meegeleverde codetabel. Ontbrekende, ongeldige of gedeelde VBO-oppervlakten laten de bouwlagenberekening open. Klassen zonder bouwlagencriterium kunnen dan nog wel worden toegekend.

<a id="bijzondere-gebouwen-en-gemalen-stap-6"></a>

#### Bijzondere functies controleren

Aanvullende bronnen kunnen de gewone BAG-klasse vervangen. De BAG-pandvorm blijft behouden.

| Klasse | Selectie |
| --- | --- |
| Kas | TOP10NL-gebouwtype `kas, warenhuis` bedekt meer dan 50% van het BAG-pand. |
| RWZI | Het representatieve pandpunt ligt strikt binnen een TOP10NL-zuiveringsterrein. Dit terrein moet een DAMO-RWZI-object raken of overlappen. Alleen de TOP10NL-laag `functioneel_gebied_vlak` doet mee. |
| Drinkwater | Het representatieve pandpunt ligt strikt binnen een beoordeeld OSM-drinkwaterterrein. Losse OSM-gebouwcontouren doen standaard niet mee. |
| Gemaal | Het gemaalpunt ligt strikt binnen precies één geselecteerd BAG-pand. Ook de gebruiksdoelen en capaciteit moeten aan de onderstaande regels voldoen. |

Voor koppeling van een gemaal aan een pand geldt:

- Alleen industrie en/of overige gebruiksfunctie: koppelen toegestaan.
- Geen VBO's of uitsluitend lege gebruiksdoelen: koppelen toegestaan.
- Wonen, andere functies, onbekende doelen of deels lege doelen: het gemaal blijft een punt.
- Geen eenduidige ruimtelijke koppeling: het gemaal blijft een punt. Er wordt geen nabijgelegen pand gekozen.

Bij meerdere gemaalregistraties in hetzelfde geschikte BAG-pand worden de capaciteiten opgeteld. Dubbele registraties met dezelfde `globalid` tellen één keer mee.

Ontbreken capaciteiten of IDs, of verschillen de capaciteiten bij dezelfde ID? Dan wordt geen totaal berekend en blijven de gemalen als punten behouden.

De totale capaciteit bepaalt de gemaalklasse. Er zijn zes capaciteitsklassen:

| Ondergrens (m³/min) | Bovengrens (m³/min) |
| ---: | ---: |
| ≥ 10 | < 20 |
| ≥ 20 | < 50 |
| ≥ 50 | < 100 |
| ≥ 100 | < 400 |
| ≥ 400 | ≤ 1.000 |
| > 1.000 | — |

Een capaciteit onder 10 m³/min krijgt geen klasse. Dat geldt ook bij een ontbrekende of ongeldige capaciteit. Een overgebleven gemaalpunt beslaat één rastercel.

##### Conflicten tussen bijzondere gebouwregels

Bij de standaardcodetabel krijgt een pand dat aan meerdere bijzondere gebouwregels voldoet geen klasse (NoData). Ook de eerder bepaalde BAG-klasse vervalt.

#### Terreinen, wegen en water indelen

| Bron | Indeling |
| --- | --- |
| BRP | Op gewascode, inclusief de opgenomen landschapselementen. |
| BGT | Wegen op functie; begroeide terreinen op fysiek voorkomen. Water en onbegroeide terreinen hebben een algemene koppeling. Oevers en slootkanten worden apart ingedeeld. |
| TOP10NL | Functionele gebieden op de volledige bronwaarde. Zowel vlakken als multivlakken doen mee. Grasland, akkerland, boomkwekerij, boomgaard en fruitkwekerij vullen de BRP-dekking aan. |

Voor BGT gelden drie voorwaarden: status `bestaand`, een lege `eindRegistratie` en een lege `objectEindTijd`. Alleen actuele registraties doen mee.

#### Codes uit de CSV

De klassen en codeparen staan in `landgebruik_met_code.csv`. De gebruikte tabel wordt bij de productie bewaard. Zie [de codetabel](../produceren/landgebruik.md#de-codetabel-aanpassen) voor de locatie en het aanpassen ervan.

- Codes 1 t/m 255 zijn landgebruiksklassen. Code 0 is NoData.
- Een bronwaarde krijgt de klasse uit de bijbehorende tabelrij. Ontbreekt die rij, dan geldt de `*`-rij, als die aanwezig is.
- De `*`-rij geldt alleen voor geldige, niet-lege bronwaarden. BRP vereist een positieve gehele gewascode.
- Een leeg bronveld in de codetabel betekent dat geen extra kenmerk nodig is voor de indeling. Zo krijgen alle actuele BGT-waterdelen de waterklasse.
- Objecten zonder koppeling in de codetabel worden overgeslagen.

De tabel levert ook de codes bij berekende gebouwfuncties. Die beslisregels liggen vast in de software.

<a id="liwo-selectie"></a>

### 2. Buitendijkse codes toekennen

Voor de buitendijkse codering worden twee LIWO-klassen geselecteerd:

- **1:** buitendijks gebied;
- **6:** regionaal onbeschermd overstroombaar gebied.

De cellen van het 25 m-raster worden omgezet naar vlakken. NoData en andere klassen vallen af.

Voor elk bronobject wordt het [representatieve punt](https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoSeries.representative_point.html) bepaald. De ligging van dit punt ten opzichte van de LIWO-selectie bepaalt de code voor het hele object:

- Binnen of op de grens van de LIWO-selectie: buitendijkse code.
- Daarbuiten: standaardcode.

De standaardcode betekent dat een object buiten deze LIWO-selectie valt. Er wordt geen afzonderlijke bescherming tegen overstromingen vastgesteld.

<a id="overlap-en-rastervoorrang"></a>

### 3. Bronnen in een vaste volgorde intekenen

Alle door een object geraakte rastercellen worden ingetekend. Daardoor kunnen ook aangrenzende vlakken dezelfde cel raken.

De tabel staat op volgorde van voorrang. Bij overlap gaat een hogere rij voor een lagere rij.

| Broncode | Bronlaag |
| --- | --- |
| 12 | BGT-waterdelen |
| 11 | Gemalen die als punt zijn behouden |
| 10 | BAG-panden met hun uiteindelijke gebouwklasse |
| 9 | BGT-wegdelen |
| 8 | BGT-ondersteunende wegdelen |
| 7 | BRP |
| 6 | TOP10NL-landbouwterreinen |
| 5 | TOP10NL-functionele gebieden: multivlak |
| 4 | TOP10NL-functionele gebieden: vlak |
| 3 | BGT-onbegroeide terreindelen |
| 2 | BGT-begroeide terreindelen |
| 1 | BGT-ondersteunende waterdelen: oever, slootkant |

- Water heeft de hoogste voorrang. Het overschrijft ook gebouwen en gemaalpunten.
- Een onopgelost BAG-pand schrijft NoData over eerder ingetekende terreinen. Later ingetekende gemaalpunten of water kunnen dit weer overschrijven.
- Bij overlap binnen dezelfde laag krijgt het laatst ingetekende object voorrang.

<a id="kleine-gaten-aanvullen-en-bronherkomst"></a>

### 4. Gaten aanvullen en controleren

Lege cellen krijgen de klasse van de dichtstbijzijnde geschikte cel binnen standaard **1 meter**, gemeten tussen celmiddens.

- Alleen lege cellen zonder broncode waarvan het celmidden binnen `landgebied` ligt, worden aangevuld.
- BAG-panden zonder klasse blijven leeg.
- BAG, BRP en TOP10NL-landbouwterreinen leveren geen cellen voor aanvulling. De overige bronlagen wel.
- Aangevulde cellen vullen geen andere gaten.
- Bij gelijke afstand wint de noordelijkste cel, daarna de westelijkste.
- Klasse én broncode worden overgenomen, inclusief een eventuele buitendijkse code.

Van twee kanten kan zo een gat van ongeveer 2 meter worden gevuld. Ook randen van grotere gaten kunnen worden aangevuld. De regel houdt geen rekening met barrières. Een klasse kan over een smal tussenliggend object heen worden overgenomen.

Na het aanvullen worden de resterende gaten vastgelegd in `nodata.gpkg`. Zie de NoData-controle onder [Uitvoer](#uitvoer).

## Uitvoer

De standaardresolutie is **0,5 meter**. Het standaard-CRS is **EPSG:28992**. Bronnen, tegelrooster en uitvoer moeten hetzelfde project-CRS gebruiken.

| Bestand | Inhoud |
| --- | --- |
| `functioneel_landgebruik.tif` en `.vrt` | Landgebruik als Cloud Optimized GeoTIFF en virtueel tegelmozaïek. Eén `uint8`-band `Landgebruik`; 0 is NoData. |
| `functioneel_landgebruik_bronnen.tif` en `.vrt` | Bronlaag per cel. Codes staan in de tabel bij [rastervoorrang](#overlap-en-rastervoorrang). Code 0 betekent geen bron. |
| `functioneel_landgebruik_bronnen.json` | Bronlegenda en instellingen voor het aanvullen. |
| `functioneel_landgebruik.qml` en `.tif.aux.xml` | QGIS-stijl en compatibiliteitskopie van de rasterattribuuttabel. Klassen en kleuren staan ook in de TIFF. |
| `nodata.gpkg`, laag `nodata` | Resterende lege rastercellen als vlakken, met `bron` en `reden`. |
| `landgebruik_met_code.csv` | De gebruikte codetabel. |

In de legenda staat de gewone klassenaam zonder toevoeging. Alleen de buitendijkse variant krijgt de toevoeging `(buitendijks)`.

Bij de standaardproductie worden ook gebouw-ID's en volledige pandvormen bewaard. Deze zijn invoer voor [DEM](dem.md). Aangrenzende panden blijven afzonderlijk herkenbaar. Ook BAG-panden zonder landgebruiksklasse behouden hun ID. Water verwijdert een gebouw-ID waar het de gebouwcel overschrijft.

**Bronnenraster**

- De broncode beschrijft de ingetekende geometrie. Een RWZI-gebouw houdt daarom BAG-code 10. Een los gemaalpunt krijgt code 11.
- De code noemt niet alle bronnen die aan de classificatie hebben bijgedragen.
- Oorspronkelijke en aangevulde cellen zijn niet afzonderlijk herkenbaar.

**NoData-controle**

- De controle volgt het eindraster, na het aanvullen.
- Alleen het deel binnen `landgebied` wordt opgenomen. Dit knipt het landgebruikraster zelf niet af.
- `bron` en `reden` verklaren open keuzes en gevonden bronuitsluitingen.
- Een gevonden uitsluiting bewijst niet dat die bron de plek had moeten vullen.
- Zonder aanwijzing staat er: *Geen bron vult deze plek.*
- Alleen aanwezige bronlagen worden onderzocht. Zonder gaten is de laag leeg.

Zie [NoData controleren](../produceren/landgebruik.md#nodata-controleren) voor het bekijken van de controle en het inschakelen bij eigen Python-bewerkingen.

## Aandachtspunten en beperkingen

- De functioneel landgebruik klasse is afgeleid uit bronregistraties; het werkelijke gebruik kan afwijken.
- Bouwlagen zijn geschat uit oppervlakten. De werkelijke verdieping van een functie is niet bekend.
- De LIWO-indeling volgt een raster van 25 meter. Een uitvoercel van 0,5 meter maakt die grens niet nauwkeuriger.
- Alle onbegroeide BGT-terreindelen krijgen dezelfde koppeling. Hun indeling als erf blijft een inhoudelijk aandachtspunt.
- Voor het herkennen van bijzondere gebouwfuncties zijn aanvullende bronnen nodig. Ontbreekt zo’n bron, dan kunnen gebouwen hun gewone BAG-classificatie behouden terwijl ze bijvoorbeeld bij een RWZI of drinkwaterproductielocatie horen.
- RWZI- en gemaalklassen zijn (nog) niet gefilterd op DAMO `statusobject`.
- BGT-vlakken zijn niet ingebrand in volgorde van de kolom `relatieveHoogteligging`.
- Bewaar de tegelbestanden zolang het VRT nodig is.

Bekijk het **bronnenraster** en **nodata.gpkg** om de indeling en ontbrekende klassen te verklaren.

## Zelf produceren

Zie [Functioneel landgebruik produceren](../produceren/landgebruik.md).
De Python-interface staat in de [API-referentie](../reference/functioneel_landgebruik.md).
