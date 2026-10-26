# Review c526692

Er zijn drie functionele problemen van ernst **Medium** opnieuw gereproduceerd. Ik adviseer deze op te lossen voordat de branch wordt samengevoegd. Alle drie de eerdere bevindingen gelden nog; deze herbeoordeling levert geen aanvullende functionele bevindingen op.

De review betreft branch `67_duikers_krijgen_geen_catchments` tegenover `main`:

- Uitvoering: 23 oktober 2026, reproducties om 09:53 UTC (11:53 Nederlandse tijd).
- Onderzochte commit: `c52669289bd303b0266fb3102e32a7b7ebb6ca84`.
- Merge-base met `main`: `273a86651964e0520560f08ca29e02e7c631f9d9`.
- Scope: de branchdiff vanaf deze merge-base, inclusief controle op lokale wijzigingen. Bij aanvang was de werkboom schoon. Bestaande, genegeerde reviewuitvoer was wel aanwezig.
- Sinds de vorige onderzochte commit `e7db72fd3fb500072876ab3886e11a658103d8ca` zijn alleen `.gitignore`, `AGENTS.md` en het reproductiescript toegevoegd of gewijzigd. Productiecode, projecttests en functionele documentatie zijn gelijk gebleven. Daarom zijn de eerdere beoordeling en controles aangevuld met hercontrole van de betreffende codepaden, nieuwe reproducties, gerichte tests en linting.

Alle voorbeelden staan in het bestaande [reproductiescript](review-e7db72f/reproduce.py). De mapnaam daarvan verwijst naar de eerdere review; de nieuwe `resultaat.json`-bestanden leggen de huidige commit vast. Er zijn geen productiedatasets nodig. Het script genereert de invoer zelf en bewaart de bestanden voordat de assertion faalt. Iedere uitvoering maakt een nieuwe outputmap. Voer de onderstaande opdrachten uit vanuit de repositoryroot, in deze checkout `D:\repositories\waterlagen`, met de pixi-omgeving `afwateringseenheden`.

## Medium — Een duiker tussen OSM-waterlopen wordt overgeslagen

De controle op duikeraansluitingen gebruikt uitsluitend primaire, secundaire en tertiaire HYDAMO-waterlopen. Aanvullende waterlopen met `rol="water"` tellen niet mee. Daardoor wordt een BGT-duiker tussen twee aansluitende OSM-waterlopen afgekeurd. De bedoelde verlaging ontbreekt en kan de afstroomroute onderbreken.

De testcase bevat twee OSM-lijnen, een BGT-duikervlak ertussen en een primaire waterloop aan het uiteinde van de rechterlijn. De ingestelde brandwaarde van de aanvullende objecten is -10 meter. De [productie-instructies](../../docs/produceren/afwateringseenheden.md), regels 161–188, beschrijven een gezamenlijke aansluitingsbeoordeling en het gebruik van de eigen brandwaarde voor aanvullende bronnen. Die bronnen mogen daarbij geen diepe HYDAMO-verbinding opleveren.

Op meetpunt `(15, 21)`, binnen de duiker, verwacht de testcase de ondiepe behandeling met 10 meter verlaging. Het voorbereide waternet geeft behandeling `0`: geen inbranding. De duiker is als `controle` geregistreerd met de reden “minder dan twee rasteraansluitingen”. De assertion op de verwachte behandeling faalt. Dit toont het ontbrekende stuk in het voorbereide netwerk; het effect op uiteindelijke afvoergebieden is niet doorgerekend.

```powershell
pixi run --as-is --environment afwateringseenheden python -B dev-workdocs/reviews/review-e7db72f/reproduce.py optional-water
```

Deze uitvoering leverde de volgende inspecteerbare bestanden op:

- [Kaart met invoer, meetpunt en berekende behandeling](review-e7db72f/output/optional-water-20261023T095310732895Z/vergelijking.png).
- [Synthetische invoer voor QGIS](review-e7db72f/output/optional-water-20261023T095310732895Z/invoer.gpkg), met lagen `primair`, `secundair` en `aanvullend`.
- [Duikerclassificatie voor QGIS](review-e7db72f/output/optional-water-20261023T095310732895Z/controle.gpkg), laag `duikers_waternet`.
- [Verwachte en berekende waarden, plus uitvoeringsgegevens](review-e7db72f/output/optional-water-20261023T095310732895Z/resultaat.json).
- [Berekend waternetraster](review-e7db72f/output/optional-water-20261023T095310732895Z/berekening/waterlopen_duikers/b6d37089c2e1ac4f127e.tif).

Neem aanvullende waterlopen mee bij het beoordelen van duikeraansluitingen. Houd de beoordeling of een HYDAMO-stelsel diep mag worden ingebrand daarvan gescheiden. De onvolledige selectie staat in [waternet.py](../../src/waterlagen/afwateringseenheden/waternet.py), regels 211–214; de selectie wordt gebruikt bij de aansluitingscontrole op regels 236–242.

## Medium — Een kruisende waterloop maakt een duikervlak onterecht geldig

Bij een duikervlak telt de code losse raakzones langs de rand als aansluitingen. Eén doorgaande waterloop die het midden van het vlak kruist, levert al twee zones op. Hierdoor wordt het hele duikervlak ingebrand, terwijl er geen waterloopeindpunt op aansluit. Dat kan een onbedoelde afstroomroute toevoegen. De [productie-instructies](../../docs/produceren/afwateringseenheden.md), regel 182, zeggen expliciet dat alleen kruisen niet genoeg is.

De testcase bevat één verticale secundaire waterloop en een horizontaal BGT-duikervlak. Op meetpunt `(15, 21)` ligt wel de duiker, maar geen waterloop. De verwachte behandeling is `0`, zonder verlaging; de duiker hoort naar controle. Het voorbereide raster geeft behandeling `3`, met 10 meter verlaging, en de duikerclassificatie is `aanvoer`. De assertion op de verwachte behandeling faalt. De onbedoelde dwarsverbinding is zichtbaar op de kaart. Het verdere hydrologische effect is niet getest.

```powershell
pixi run --as-is --environment afwateringseenheden python -B dev-workdocs/reviews/review-e7db72f/reproduce.py crossing
```

Bekijk de volgende bestanden:

- [Kaart met de kruising en onbedoelde dwarsverbinding](review-e7db72f/output/crossing-20261023T095310732416Z/vergelijking.png).
- [Synthetische invoer voor QGIS](review-e7db72f/output/crossing-20261023T095310732416Z/invoer.gpkg).
- [Duikerclassificatie voor QGIS](review-e7db72f/output/crossing-20261023T095310732416Z/controle.gpkg).
- [Verwachte en berekende waarden, plus uitvoeringsgegevens](review-e7db72f/output/crossing-20261023T095310732416Z/resultaat.json).
- [Berekend waternetraster](review-e7db72f/output/crossing-20261023T095310732416Z/berekening/waterlopen_duikers/b6d37089c2e1ac4f127e.tif).

Onderscheid daadwerkelijke aansluitingen van een doorgaande kruising voordat randcontacten als twee aansluitingen worden geaccepteerd. De huidige telling staat in [waternet.py](../../src/waterlagen/afwateringseenheden/waternet.py), regels 124–135. Deze functie is met de branch toegevoegd.

## Medium — Een lege duikerlaag kan een bestaande waterloop verwijderen

Dit gebeurt bij invoer zonder `bron_id`, `globalid` of `code`, wanneer de dataframe-index bijvoorbeeld `42` is. De voorbereiding maakt nieuwe records en leidt daarna de bronidentificatie af van de nieuwe index. De latere selectie gebruikt juist de oorspronkelijke index. De identificaties komen niet overeen, waardoor de waterloop uit de uitvoer wordt gefilterd.

De testcase geeft één lijn van 20 meter door. Zonder de duikerparameter komt één segment terug. Met een lege `duikersifonhevel`-laag blijven nul segmenten over. Verwacht is dat dezelfde lijn behouden blijft, omdat er geen duikers zijn die hem kunnen veranderen. De assertion `len(actual) == 1` faalt. De waterloop is daarmee aantoonbaar niet meer beschikbaar als afwateringsdoel. De standaard bronlezer vult al bronidentificaties in; deze bevinding betreft de ondersteunde Python-aanroep met index als terugval.

```powershell
pixi run --as-is --environment afwateringseenheden python -B dev-workdocs/reviews/review-e7db72f/reproduce.py empty-culverts
```

Bekijk de [kaart met verwacht en berekend resultaat](review-e7db72f/output/empty-culverts-20261023T095310732056Z/vergelijking.png), het [GeoPackage](review-e7db72f/output/empty-culverts-20261023T095310732056Z/vergelijking.gpkg) en de [uitvoeringsgegevens](review-e7db72f/output/empty-culverts-20261023T095310732056Z/resultaat.json). Het GeoPackage bevat de lagen `invoer`, `verwachte_geometrie`, `zonder_duikerparameter` en `met_lege_duikers`; de laatste laag is leeg. De oorspronkelijke index staat als `invoerindex` bij de opgeslagen invoer. Het script stelt die index zelf in bij reproductie.

Leid de bronidentificatie af voordat de oorspronkelijke index verloren gaat en gebruik die consequent in zowel de voorbereiding als de doelselectie. Het wegfilteren gebeurt in [workflow.py](../../src/waterlagen/afwateringseenheden/workflow.py), regels 158–161, in het nieuw toegevoegde duikerpad. Het opnieuw opbouwen van records gebeurt in [lines.py](../../src/waterlagen/afwateringseenheden/lines.py), regels 136–146. De test verlangt behoud van de geometrie, niet een specifieke nieuwe identificatiewaarde.

## Controles en grenzen van deze review

De drie bovenstaande opdrachten zijn daadwerkelijk uitgevoerd op `c526692` en eindigen elk met een `AssertionError` door het beschreven gedrag. Imports, gegevensopbouw en opslag van resultaten slagen. De drie PNG-bestanden zijn geopend en visueel gecontroleerd. De GeoPackages zijn opnieuw gelezen; de waternetrasters zijn gecontroleerd op vier banden, 20 × 20 cellen, een resolutie van 2 meter en CRS `EPSG:28992`. De rasterbanden bevatten achtereenvolgens behandeling, broncode, doeluitsluiting en ondiepe branddiepte. De getoonde verlagingen zijn sturing voor de berekening, geen werkelijke bodemhoogtes.

De bestaande gerichte tests slagen: **68 passed**, met 255 waarschuwingen over toekomstige wijzigingen in matrixvermenigvuldiging. Uitgevoerde opdracht in PowerShell:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
pixi run --as-is --environment afwateringseenheden pytest -q -p no:cacheprovider tests/test_afwateringseenheden_waternet.py tests/test_afwateringseenheden_watersysteem.py
```

Ruff meldt **25 overtredingen** in de gewijzigde Python-bestanden, waaronder importvolgorde, exceptiongebruik en vereenvoudigingen. Het reproductiescript krijgt geen melding. Er zijn geen automatische fixes uitgevoerd. Deze meldingen zijn niet als afzonderlijke functionele bugs meegeteld:

```powershell
$reviewPythonFiles = @(git diff --name-only --diff-filter=ACMR main...HEAD -- '*.py')
pixi run --as-is --environment afwateringseenheden ruff check --no-cache --output-format concise @reviewPythonFiles
git diff --check main...HEAD
```

De laatste opdracht slaagt. Pixi meldt een niet-bestaande map voor `SSL_CERT_DIR`; dit heeft deze lokale controles niet geblokkeerd. Er waren geen downloads of externe diensten nodig.

De eerdere bredere controle op de ongewijzigde productiecode van `e7db72f` leverde 415 geslaagde tests en een geslaagde strikte documentatiebuild op. Die volledige set en de documentatiebuild zijn in deze uitvoering niet herhaald. Er is geen nieuwe coverage-meting uitgevoerd; de vereiste 90% dekking is hiermee niet aangetoond. De review omvat geen volledige productie met AHN of landelijke datasets. De genoemde gevolgen voor complete afvoergebieden blijven daarom risico's op basis van de gereproduceerde fouten in de voorbereiding.

## Documentatie

Documentatie-impact: **`confirmed`**. De beschermde [functionele beschrijving](../../docs/bewerkte-lagen/afwateringseenheden.md) is niet overal in overeenstemming met de implementatie:

- Regel 29 zegt dat de standaardproductie geen aanvullend beheerderfilter gebruikt. [productie.py](../../src/waterlagen/afwateringseenheden/productie.py), regels 242–247, geeft de beheerdersselectie door; [sources.py](../../src/waterlagen/afwateringseenheden/sources.py), regels 295–302, past die op doelen en punten toe. De documentatie moet het onderscheid tussen volledige inbrandcontext en geselecteerde afwateringsdoelen uitleggen.
- Regels 52–53 beschrijven nog de algemene branddiepteverhouding en het inbranden van segmenten zonder de nieuwe duikeruitzonderingen. [waternet.py](../../src/waterlagen/afwateringseenheden/waternet.py), in `prepare_waternet`, onderscheidt verbonden en losliggende stelsels en duikers die van doelen worden uitgesloten. De actuele regels staan al uitgebreider in de [productie-instructies](../../docs/produceren/afwateringseenheden.md), regels 161–188, maar ontbreken in de canonieke functionele uitleg.

De pagina heeft `editorial_status: human` en is niet aangepast. Laat deze verschillen inhoudelijk beoordelen en werk de functionele uitleg bij; beschouw de code niet automatisch als juiste bron wanneer die met de afgesproken verwerking botst.

Deze reviewuitvoering heeft uitsluitend dit rapport en nieuwe reproductieresultaten toegevoegd. Bestaande bestanden, scripts, tests, productiecode en Git-configuratie zijn tijdens de review niet gewijzigd; tijdens de review zijn geen commits gemaakt. Het rapport en het reproductiescript worden in Git bijgehouden. De gegenereerde uitvoer blijft genegeerd en is lokaal beschikbaar via de links hierboven; andere ontwikkelaars kunnen met de genoemde opdrachten nieuwe resultaten genereren.
