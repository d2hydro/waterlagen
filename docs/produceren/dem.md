# DEM produceren

Begin met vier aangrenzende tegels rond Alkmaar. Het script `scripts/dem.py`
selecteert een 2×2-blok uit `tiles.gpkg` van een bestaande landgebruikrun,
rond RD-coördinaat `(111000, 516000)`. Bij het huidige 5000m-rooster zijn dit
de vier tegels tussen `(105000, 510000)` en `(115000, 520000)`. De resolutie,
codetabel en bronpaden worden uit die run overgenomen.

## Vooraf

Gebruik de [ontwikkelomgeving](../bijdragen/ontwikkelomgeving.md) van deze
repository. Zorg dat de [landgebruikbronnen](landgebruik.md) zijn voorbereid.
De opgegeven landgebruikrun moet `run.json`, `tiles.gpkg` en
`landgebruik_met_code.csv` bevatten.

Oudere landgebruikrasters hebben geen gebouw-ID's. Met `--prepare-landuse`
worden uitsluitend de vier geselecteerde landgebruiktegels opnieuw geproduceerd
in de nieuwe DEM-runfolder. De bestaande landgebruikrun blijft behouden.
Deze stap maakt ook de gedeelde gebouw-ID-index en volledige gebouwgeometrieën.
De voorbereide gebouwomgeving omvat bovendien de maximale gebouwzoekafstand,
ook rond panddelen buiten de geselecteerde tegelkernen. Bij een grotere
zoekafstand moet deze omgeving opnieuw worden voorbereid.

## Alkmaar-proef uitvoeren

Voer vanuit de repositoryroot uit, met het pad naar uw eigen landgebruikrun:

```powershell
pixi run python scripts/dem.py --landuse-run "data/processed_data/functioneel_landgebruik/nederland/MIJN_RUN" --prepare-landuse --run-id alkmaar_proef --workers 1
```

De uitvoer komt onder `processed_data/dem/alkmaar/alkmaar_proef`. Gebruik
`--output-root data/dem_validation` voor een afzonderlijke lokale uitvoerroot.
Het script downloadt ontbrekend AHN-DTM voor de vier tegels en hun donoromgeving
in de gedeelde AHN-bronmap van de datastore. Bestaande geldige tegels worden
hergebruikt. `input/ahn.vrt` binnen de run verwijst alleen naar de geselecteerde
brontegels. Een bestaand, volledig dekkend DTM-mozaïek kan met
`--ahn-vrt PAD` worden gebruikt. Er wordt geen landelijke DEM-productie gestart.

Als de landgebruikrun al passende gebouw-ID's en gebouwgeometrieën heeft,
kan `--prepare-landuse` achterwege blijven.

## Instellingen

| CLI-optie | Standaard | Betekenis |
| --- | --- | --- |
| `--building-initial-buffer-m` | 1 | Eerste gebouwzoekafstand |
| `--building-buffer-step-m` | 1 | Toename zonder geldige donor |
| `--building-percentile` | 75 | Percentiel bij eerste geslaagde zoekactie |
| `--building-max-search-distance-m` | 5 | Maximale gebouwzoekafstand |
| `--interpolation-max-distance-m` | 250 | Maximale AHN-interpolatieafstand; 0 schakelt deze uit |
| `--workers` | 1 | Aantal workers voor landgebruikvoorbereiding |

De DEM-tegels worden achtereenvolgens verwerkt om het geheugengebruik te
begrenzen. Er is geen DEM-landmasker. De betekenis van de resultaten en de
NoData-afhandeling staan bij [DEM met gebouwen](../bewerkingen/dem.md).

## Controleren en hervatten

Het script controleert na afloop alle pixels van `dem.vrt` tegenover `dem.tif`
en van `dem_bron.vrt` tegenover `dem_bron.tif`, inclusief grid en schaalmetadata.
Inspecteer daarnaast de gebouwhoogten en de geometrieën in `nodata.gpkg`.
Een geslaagde technische controle betekent niet dat alle gaten zijn opgelost.

Hervat dezelfde opdracht met `--resume` en dezelfde `--run-id` en instellingen.
Voltooide, passende tegelsets en gebouwhoogten worden hergebruikt; ontbrekende
of onderbroken DEM-tegelsets worden opnieuw gemaakt. Een landgebruiktegel met
ontbrekende gebouwcompanions moet expliciet opnieuw worden opgebouwd.
`--overwrite` herberekent uitvoer binnen dezelfde runidentiteit; gewijzigde
bronnen of instellingen vereisen een nieuwe run-ID.

Voor een groter gebied kan de [Python-API](../reference/dem.md) een expliciete
lijst bestaande landgebruiktegels verwerken. Gebruik dit pas na controle van
het Alkmaar-resultaat; het script zelf blijft beperkt tot de vier proeftegels.
