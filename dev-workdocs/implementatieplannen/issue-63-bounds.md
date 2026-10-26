---
editorial_status: ai
---

# #63 — Vrije gebiedsselectie via de productie-CLI

**Status:** geïmplementeerd op branch `63_gebieden_met_bounds`.
De gebruiker heeft de onderstaande functionele keuzes bevestigd.

Aanleiding: [#63 Testgebieden](https://github.com/d2hydro/waterlagen/issues/63),
met het punt `(184785, 392554)` en de tekst “Met brandlaag”. Het issue bevat
ook een kaartbeeld, maar geen brandbestand of vastgelegde verwachte uitkomst.
Dit plan is opgesteld op branch `issue/65_brandlagen`, op basis van de daar
aanwezige optionele brandlagen. Het schrijft geen nieuwe branch of PR-volgorde voor.

Dit is een intern werkdocument, uitgesloten van de gepubliceerde MkDocs-site.

## Doel en vastgelegde keuzes

Een gebruiker bewerkt eigen brandlagen in QGIS, draait de gewone
afwateringseenheden-CLI voor een zelf gekozen gebied en inspecteert de uitvoer
in QGIS. Een PowerShell-script bewaart de opdracht voor een volgende uitvoering.
Meer gebieden kunnen met dezelfde CLI en eigen scripts worden verwerkt.

De ontwerpafspraken zijn:

- Voeg `--bounds xmin ymin xmax ymax` toe aan alle vijf gedeelde
  productiecommando's: `afwateringseenheden`, `dem`,
  `functioneel_landgebruik`, `inwoners` en `autos`.
- Maak van de bounds een bbox-polygoon in `settings.crs`, momenteel standaard
  `EPSG:28992`. Combineer bounds niet met `--area` of `--waterbeheercode`.
- Gebruik de polygoon als bestaande gebiedsselectie. Selecteer volledige
  kerntegels of objecten volgens het betreffende product; knip uitvoer niet af.
- Behoud bij afwateringseenheden de huidige kerntegels van 10 × 10 km,
  2 km buffer, 2 m resolutie en bestaande grid-oorsprong. De CLI biedt nu geen
  tegelgrootte-optie; dit plan voegt die niet toe.
- Gebruik `xmin_ymin_xmax_ymax` als gebiedsmap, met daaronder de bestaande runmap.
- Behoud de bestaande brandlagen-TOML: één of meer GeoPackages, met één of meer
  expliciet aangewezen lagen per bestand.
- Lever een eenvoudig `.ps1`-voorbeeld rond het punt uit #63.

De oorspronkelijke term gebruikstest beschrijft hier het handmatige gebruik.
Er komt geen verzameling testcases, testrunner, automatische vergelijking,
acceptatierapport of configuratieformaat voor tests. De gebruiker kan zelf runs
met en zonder optionele brandlagen starten en in QGIS vergelijken. De vaste
HYDAMO-inbranding blijft ook zonder optionele brandlagen actief.

## Bestaande bouwstenen en wijzigingspunten

| Bestand | Relevante bestaande werking |
| --- | --- |
| `src/waterlagen/_cli.py` | `production_parser` en `run_cli` worden door alle vijf productiecommando's gebruikt. De parser heeft al een exclusieve gebiedskeuze; `run_cli` maakt daar nu altijd een naamstring van. |
| `src/waterlagen/areas.py` | `ProductionArea` bevat naam, geometrie en CRS. `identity` legt geometrie en CRS vast. `area_name` accepteert nu ook voor dit object alleen bekende namen of waterschapscodes. |
| `src/waterlagen/_production.py` | Productiemappen, bronidentiteit, runstatus, hervatten en standaard UTC-run-ID bestaan al. |
| `src/waterlagen/afwateringseenheden/productie.py` | Selecteert volledige 10 km-tegels, bereidt hun context voor en verwerkt optionele brandlagen. |
| `src/waterlagen/dem/workflow.py` | Geeft gebiedsselectie ook door aan eventueel benodigde landgebruikproductie. |
| `src/waterlagen/_cbs_production.py` | Gebruikt de gebiedsgeometrie voor inwoners en auto's; volledige geselecteerde CBS-buurten blijven behouden. |

De publieke productie-ingangen accepteren al `ProductionArea`. Hergebruik dit
object; voeg geen afzonderlijk bounds-argument aan elk product toe. Houd
geometrieconstructie, validatie en naamgeving centraal in `areas.py`.

## CLI- en gebiedscontract

### Invoer en validatie

`--bounds` accepteert precies vier eindige getallen in de volgorde
`xmin ymin xmax ymax`. Vereis `xmin < xmax` en `ymin < ymax`. Weiger ontbrekende
waarden, niet-numerieke waarden, `NaN`, oneindig, omgekeerde grenzen en
rechthoeken zonder oppervlakte met een duidelijke CLI-fout vóór productie,
downloads of het aanmaken van uitvoermappen.

Gebruik het ingestelde project-CRS en vermeld dit in help en documentatie.
Er komt geen automatische CRS-detectie of afzonderlijke `--bounds-crs`-optie.
De voorbeeldcoördinaten uit #63 worden gebruikt als RD-coördinaten; de
voorbeeldinstructie moet daarom `settings.crs = EPSG:28992` als uitgangspunt noemen.

De drie gebiedsopties sluiten elkaar wederzijds uit. Zonder gebiedsoptie blijft
Nederland de standaard. Laat de standaardwaarde van `--area` een expliciete
bounds-selectie niet overschrijven. Bestaande gebiedsnamen en waterschapscodes
houden hun gedrag en validatie.

### Geometrie en naam

Voeg een kleine, getypeerde helper in `areas.py` toe om de vier grenzen te
valideren en een `ProductionArea` met bbox-polygoon en project-CRS te maken.
Gebruik bestaande geometrie- en CRS-controles in `resolve_area`.

Genereer de gebiedsnaam uit de ingevoerde bbox, niet uit de geselecteerde
kerntegels. Gebruik een vaste numerieke notatie met een punt als decimaalteken.
Gehele waarden krijgen geen `.0`; equivalente invoer zoals `1` en `1.0`
levert dezelfde naam op. Normaliseer negatieve nul naar nul en voorkom
afronding waardoor verschillende representabele grenzen dezelfde naam krijgen.
Decimalen en negatieve coördinaten zijn toegestaan.

Breid `area_name` gericht uit zodat het geconstrueerde `ProductionArea` met
deze naam door de bestaande productievoorcontrole komt. Accepteer geen
willekeurige paden als gebiedsnaam. Houd de gewone `--area`-invoer beperkt tot
zijn bestaande gebiedsnamen en codes; bounds zijn een expliciete andere ingang.

Laat `run_cli` het volledige `ProductionArea` doorgeven. Behoud de bestaande
identiteit met geometriehash en CRS in `run.json` en de controles op
compatibiliteit bij hervatten. De gebiedsmap alleen is geen volledige identiteit.

### Selectie en rekenomgeving

Verander bestaande selectieregels niet. Bij tegelproducten selecteert de bbox
volledige overlappende kerntegels. Alleen aanraking aan een tegelrand mag geen
extra tegel selecteren. Houd oorsprong, resolutie en productbuffers gelijk.
Inwoners en auto's blijven volledige intersecterende CBS-buurten verwerken.

Een klein gebied kan nog steeds grote berekeningen en landelijke
bronbestanden vereisen. De bbox is geen downloadlimiet of uitvoerclip.

## Resultaatmappen en herhaald gebruik

Voorbeeld met een selectie van 1 × 1 km rond het issuepunt:

```text
processed_data/afwateringseenheden/
└── 184285_392054_185285_393054/
    └── YYYYMMDDTHHMMSSZ/
        ├── afwateringseenheden.gpkg
        ├── watersysteem.gpkg
        ├── run.json
        ├── productie.log
        └── tiles/
```

Deze selectie ligt binnen de bestaande 10 km-kern
`(180000, 390000, 190000, 400000)`. Met buffer blijft de rekenomgeving
14 × 14 km; de 1 km-selectie verkleint de kern niet.

Hergebruik `_production.py` zonder een tweede runbeheermechanisme. Zonder
`--run-id` ontstaat een UTC-tijdstempel met secondenprecisie. De bestaande
fout bij een naamconflict blijft bestaan; beloof geen unieke naam bij meerdere
starts in dezelfde seconde.

Na het opslaan van QGIS-wijzigingen draait de gebruiker opnieuw zonder vaste
run-ID. Bestaande broncaches blijven bruikbaar; de berekening krijgt een nieuwe
uitvoermap. `--resume` is voor een onderbroken run met dezelfde invoer.
Gewijzigde brandbestanden vereisen een nieuwe run, ook bij `--overwrite`.
Verander dit bestaande contract niet. Bewerk invoer niet tijdens een run.

## PowerShell-voorbeeld en gebruikersworkflow

Voorgestelde locatie voor het uitvoerbare voorbeeld:
`docs/produceren/voorbeelden/afwateringseenheden_issue63.ps1`.
De implementatie voegt dit bestand toe en linkt ernaar vanuit de
productie-instructies. Het script is beschikbaar op deze locatie.

Zet de vier bounds en het pad naar de brandlagen-TOML als herkenbare variabelen
bovenaan. Gebruik bovengenoemde 1 km-bbox als aanpasbaar voorbeeld. Start
vanuit de repositoryroot één normale productieopdracht met PCRaster:

```console
pixi run --environment afwateringseenheden afwateringseenheden --bounds 184285 392054 185285 393054 --brandlagen-config PAD_NAAR_BRANDLAGEN.toml
```

Deze aanroep is beschikbaar met de geïmplementeerde `--bounds`-optie.

Het script bevat geen vaste run-ID, vergelijking, downloadvernieuwing of
automatische hervatting. Geef argumenten veilig als afzonderlijke waarden door,
ook bij paden met spaties, en geef een niet-nul exitcode van pixi door. Documenteer
vanuit welke werkdirectory het script draait en hoe het configuratiepad wordt
opgelost. Relatieve GeoPackage-paden in TOML blijven relatief aan dat TOML-bestand.

De gebruiker verzorgt zelf de bestanden en lagen. Verwijs naar het bestaande
TOML-voorbeeld; verzin geen brandgeometrie of gewenste hydrologische uitkomst
voor het punt. De gebruikersstappen zijn:

1. GeoPackage-lagen, attributen en laagselectie in QGIS/TOML voorbereiden.
2. Wijzigingen opslaan en het PowerShell-script uitvoeren.
3. De gelogde resultaatmap openen en de gewenste GIS-uitvoer in QGIS laden.
4. Brandlagen bijstellen en opnieuw uitvoeren voor een nieuwe runmap.

## Implementatiestappen

1. Voeg de centrale bbox-constructie, invoervalidatie en canonieke gebiedsnaam
   toe aan `areas.py`. Pas de verwerking van `ProductionArea` gericht aan.
2. Voeg `--bounds` aan de gedeelde parser toe en geef vanuit `run_cli` het
   geconstrueerde gebiedsobject aan de productie-ingang door.
3. Controleer alle vijf productieroutes, inclusief DEM naar automatische
   landgebruikproductie, op behoud van geometrie, CRS, gebiedsmap en selectie.
   Wijzig productcode alleen wanneer deze nieuwe gebiedsvorm dat nodig maakt.
4. Voeg het PowerShell-voorbeeld toe en werk de bewerkbare documentatie bij.
5. Voer de onderstaande gerichte ontwikkelcontroles uit. Een echte
   afwateringsberekening voor #63 volgt als gebruikershandeling zodra de
   gebruiker de eigen brandlagen heeft aangeleverd.

## Ontwikkeltests en controles

Deze tests controleren de softwarewijziging. Ze vormen geen nieuwe voorziening
voor de handmatige QGIS-workflow en gebruiken geen echte downloads.

- Breid `tests/test_production_cli.py` uit voor bounds bij alle vijf
  commando's, de helptekst, exclusiviteit van gebiedsopties, behoud van
  Nederland als standaard en doorgifte van geometrie en CRS. Controleer ook
  bounds samen met `--brandlagen-config`.
- Test bbox-validatie, veilige canonieke namen, equivalente getalnotaties,
  decimalen en negatieve nul bij de gedeelde gebiedstests. Controleer dat
  ongeldige invoer de workflow niet start en geen uitvoermap maakt.
- Breid waar nodig `tests/test_production_sources.py` en
  `tests/test_afwateringseenheden_script.py` uit voor een bbox-gebied zonder
  administratieve grenslookup voor de selectie. De landsgrens die verwerking
  zelf nodig heeft blijft een afzonderlijke bron. Controleer de 10 km-kern,
  buffercontext, ongeknipte uitvoer en bestaande grensaanrakingsregels.
- Controleer met kleine fixtures/mocks de productiemap en runidentiteit in
  `tests/test_production.py`, de gebiedsdoorgifte aan landgebruik in
  `tests/test_dem_inputs.py`/`tests/test_dem.py` en volledige buurtselectie
  bij inwoners/auto's. Behoud bestaande controles op gewijzigde broninvoer.
- Controleer de PowerShell-syntaxis en de argumenten met een vervangende
  pixi-opdracht, zonder productie te starten; controleer ook foutdoorgifte.
  Voeg geen tests toe die alleen de scripttekst dupliceren.

Voer de direct geraakte bestanden uit met `pixi run pytest ...` en draai Ruff
op de gewijzigde Python-bestanden. Bouw de documentatie met
`pixi run --environment docs docs-build`. Draai daarnaast
`tests/test_python_examples.py` als de gedeelde gebiedswijzigingen of
voorbeeldinclusies die bestaande voorbeelden raken.

## Documentatie en acceptatie

Werk bij implementatie de volgende bewerkbare pagina's bij:

- `docs/produceren/cli.md`: canonieke uitleg van bounds, CRS, exclusiviteit en
  behoud van volledige tegels/objecten.
- `docs/produceren/configuratie.md`: gebiedsmap op basis van bounds en de
  bestaande UTC-runmappen.
- `docs/produceren/afwateringseenheden.md`: QGIS–CLI–QGIS-workflow en het
  downloadbare PowerShell-voorbeeld; link naar de gedeelde gebiedsuitleg.
- Relevante publieke docstrings en `docs/reference/productie.md`: de nieuwe
  gebiedsconstructie, voor zover deze een publieke Python-interface krijgt.

De beschermde pagina `docs/bewerkte-lagen/afwateringseenheden.md` blijft
ongewijzigd. De bestaande omissie over optionele brandlagen is al vastgelegd
in [het plan voor #65](issue-65-brandlagen.md); dit plan verleent geen
toestemming om beschermde tekst aan te passen. De bestaande uitleg over
volledige tegels wordt door bounds op zichzelf niet gewijzigd.

De implementatie is gereed wanneer alle vijf CLI's een geldige bbox accepteren,
ongeldige of conflicterende selectie vóór productie wordt afgewezen, de
gebiedsmap de canonieke ingevoerde bounds bevat en bestaande productselectie,
runbeheer en brandlagenverwerking behouden blijven. Het PowerShell-voorbeeld
en de uitvoerinstructies moeten zonder Python-script bruikbaar zijn.
Een inhoudelijk goede afwatering rond het issuepunt is geen conclusie die
uitsluitend uit deze ontwikkeltests kan worden getrokken.

Documentatie-impact: **confirmed**. Dit bestand legt het interne plan vast;
de toekomstige implementatie verandert de publieke CLI en uitvoerinstructies.
Houd de implementatieplannen onder `dev-workdocs/implementatieplannen/`, buiten `docs/`.
