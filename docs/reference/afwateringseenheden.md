---
editorial_status: ai
---

# Afwateringseenheden in Python

Voor een volledige berekening gebruikt u de [productiefunctie voor afwateringseenheden](productie.md#afwateringseenheden). [Uitvoer bekijken in QGIS](../produceren/afwateringseenheden.md#controle-in-qgis).

## Zelf tegels berekenen

<a id="rekenbuffer-instellen"></a>
Met `calculate_afwateringseenheden_tiles` kiest u zelf de rekenbuffer (`tile_buffer_m`, standaard 2.000 m). Lever een voorbereid watersysteem en een AHN-VRT die ook de buffer dekken. Met `clip_to_area=False` behoudt u de hele kerntegels, zoals bij een productierun.

[Bekijk het voorbeeldscript](bewerkte-lagen-produceren.md#afwateringseenheden){ .md-button }

??? info "Tegelberekening · `calculate_afwateringseenheden_tiles`"

    ::: waterlagen.afwateringseenheden.calculate_afwateringseenheden_tiles

<a id="randfilter-en-aanvulling"></a>

??? info "Hoe wordt een gat tussen tegels aangevuld?"

    Bij een gat krijgt de buurtegel met de grootste dekking voorrang. Bij gelijke dekking telt eerst de afstand tot de rekenrand en dan de tegel-ID. [Werking van het randfilter](../bewerkte-lagen/afwateringseenheden.md#tegels-buffers-en-samenvoegen).

<a id="duikervoorbereiding"></a>

??? info "Wanneer koppelt een duiker aan de primaire waterlopen?"

    `prepare_watersysteem` koppelt een duiker als beide uiteinden binnen de koppelafstand liggen (standaard 0,5 m) en de primaire waterlopen een aansluitende route langs de duiker vormen. [Waterlopen en duikers inbranden](../bewerkte-lagen/afwateringseenheden.md#waterlopen-en-duikers-inbranden).

<a id="parallelle-routes"></a>

??? info "Parallelle routes met kunstwerken instellen"

    Met `prepare_watersysteem(..., max_complex_routelengte=100.0)` stelt u de maximale lengte voor parallelle routes met kunstwerken in. Gebruik `0` om deze selectie uit te schakelen. [Werking en kaartcontrole](../produceren/afwateringseenheden.md#parallelle-routes-instellen).

## Signaalkaart opnieuw maken

Gebruik `write_duiker_signaalkaart(run_dir)` om de signaalkaart van een bestaande run te vernieuwen. [Welke duikers komen op de kaart?](../produceren/afwateringseenheden.md#signaalkaart-beoordelen)

??? info "Signaalkaart · `write_duiker_signaalkaart`"

    ::: waterlagen.afwateringseenheden.write_duiker_signaalkaart

<span id="brandlagen-meegeven"></span>

??? info "Een brandlagenbestand meegeven"

    Lees het TOML-bestand en geef de configuratie mee aan dezelfde productiefunctie:

    ```python
    from pathlib import Path
    from waterlagen.afwateringseenheden import read_brandlagen_config

    brandlagen = read_brandlagen_config(Path("brandlagen.toml"))
    ```

    Geef de configuratie als `brandlagen=brandlagen` mee aan de productiefunctie.

    [Download een voorbeeld-TOML](voorbeelden/brandlagen.toml){ .md-button .md-button--primary download="brandlagen.toml" }
