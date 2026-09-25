# %%
"""Bekijk alle BAG-controlekeuzes in een bestand met een pandenlaag."""

import tempfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

from waterlagen import _geopandas as wgpd
from waterlagen._crs import same_crs
from waterlagen._downloads import validate_geopackage
from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik import FunctioneelLandgebruikLayers
from waterlagen.functioneel_landgebruik.bag_panden_en_verblijfsobjecten import (
    BagSourceData,
    _bounds_including_panden,
    read_bag_source_data,
)
from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import (
    classify_bag_panden,
    prepare_gemalen,
)
from waterlagen.functioneel_landgebruik.gemalen import link_pumping_stations
from waterlagen.functioneel_landgebruik.kassen_rwzi_drinkwater import (
    SpecialBuildingSources,
)
from waterlagen.functioneel_landgebruik.landgebruikstabel import (
    DEFAULT_MAPPING_CSV,
    LanduseTable,
    load_landuse_table,
)
from waterlagen.settings import settings

# Flik-Flak, Marathonloop, 's-Hertogenbosch; voorbeeld notitie p. 5.
# Pand 0796100000258450 en alle vier gekoppelde verblijfsobjecten liggen hierin.
# xmin, ymin, xmax, ymax in EPSG:28992, met ruimte rondom het pand.
BOUNDS = (150000.0, 414720.0, 150220.0, 414910.0)

# Eigen controlevoorbeeld bij de winkel/wonen-regel uit de notitie, p. 4–5.
# Vughterstraat 88/88A: pand 0796100000235598, winkel 80 m² + woning 146 m².
WINKEL_WONING_BOUNDS = (148940.0, 410840.0, 149020.0, 410920.0)

# Alle stappen blijven herkenbaar als kolommen in dezelfde laag.
STAP = (
    6  # 1 bron; 2 status; 3 functie; 4 bouwlagen; 5 BAG-klasse; 6 bijzondere gebouwen.
)
LANDGEBRUIK_CSV = DEFAULT_MAPPING_CSV  # Pas aan voor een eigen CSV-bestand.


def _process_area(
    bag: BagSourceData,
    name: str,
    stap: int,
    *,
    table: LanduseTable | None = None,
    special_sources: SpecialBuildingSources | None = None,
) -> gpd.GeoDataFrame:
    """Run the requested steps and retain excluded panden for inspection."""
    controle = bag.panden.copy()
    controle["uitsnede"] = name
    controle["controle_tot_stap"] = stap
    if stap >= 2:
        keuzes = classify_bag_panden(
            bag, through_step=stap, table=table, special_sources=special_sources
        )
        controle["meegenomen_stap2"] = controle.index.isin(keuzes.index)
        controle["reden_statusselectie"] = (
            "Uitgesloten: pandstatus niet toegestaan volgens notitie p. 4"
        )
        controle.loc[controle["meegenomen_stap2"], "reden_statusselectie"] = (
            "Meegenomen: pandstatus toegestaan volgens notitie p. 4"
        )
        ontbreekt = controle["status"].fillna("").astype(str).str.strip() == ""
        controle.loc[ontbreekt, "reden_statusselectie"] = (
            "Uitgesloten: pandstatus ontbreekt"
        )
        # Add only new decision columns; all original panden remain visible.
        for column in keuzes.columns:
            if column not in controle.columns:
                controle[column] = keuzes[column].reindex(controle.index)
        for column in ["functiekeuze_status", "bouwlagen_status", "klasse_status"]:
            if column in controle.columns:
                controle[column] = controle[column].astype("object")
                controle.loc[~controle["meegenomen_stap2"], column] = (
                    "niet uitgevoerd: uitgesloten in stap 2"
                )
    if stap >= 5:
        controle["toelichting_resultaat"] = controle["reden_klasse"].astype("object")
        functie_open = (
            controle["functiekeuze_status"] == "nog te beoordelen"
        ) & controle["lgb_koppeling_id"].isna()
        if stap >= 6:
            functie_open &= controle["bijzondere_koppelingen"].fillna("").eq("")
        controle.loc[functie_open, "toelichting_resultaat"] = (
            "Nog geen klasse: "
            + controle.loc[functie_open, "reden_functiekeuze"].astype("string")
        )
        uitgesloten = ~controle["meegenomen_stap2"]
        controle.loc[uitgesloten, "toelichting_resultaat"] = controle.loc[
            uitgesloten, "reden_statusselectie"
        ]
    return controle


def _write_control(
    controle: gpd.GeoDataFrame, target: Path, *, gemalen: gpd.GeoDataFrame | None = None
) -> None:
    """Validate a temporary GeoPackage before atomically replacing the target."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".bag_controle_", dir=target.parent
    ) as work:
        temporary = Path(work) / target.name
        controle.to_file(temporary, layer="bag_controle", driver="GPKG")
        if gemalen is not None:
            gemalen.to_file(temporary, layer="gemalen_controle", driver="GPKG")
        validate_geopackage(temporary)
        written = wgpd.read_file(temporary, layer="bag_controle")
        if len(written) != len(controle) or set(written.columns) != set(
            controle.columns
        ):
            raise ValueError("Controle van de geschreven pandenlaag is mislukt.")
        temporary.replace(target)


def main(
    data_store: DataStore | None = None,
    *,
    bounds: tuple[float, float, float, float] | None = None,
    overwrite: bool = False,
    stap: int = STAP,
    mapping_csv: Path | None = None,
    special_sources: SpecialBuildingSources | None = None,
    gemalen_gpkg: Path | None = None,
    target_path: Path | None = None,
) -> Path:
    """Write one control layer for both examples, or custom bounds.

    Existing output is reused unless overwrite=True. The step argument limits
    calculations; excluded panden remain visible with empty later results.
    mapping_csv overrides LANDGEBRUIK_CSV for the step-5 codes.
    target_path optionally selects a separate control GeoPackage.
    """
    if stap not in (1, 2, 3, 4, 5, 6):
        raise ValueError(
            "Kies stap 1 (bron), 2 (status), 3 (functie), 4 (bouwlagen), 5 (BAG-klasse) of 6 (bijzondere gebouwen)."
        )
    if not same_crs(settings.crs, "EPSG:28992"):
        raise ValueError("Dit controlescript verwacht RD-coördinaten (EPSG:28992).")
    areas = (
        [("Flik-Flak", BOUNDS), ("Vughterstraat", WINKEL_WONING_BOUNDS)]
        if bounds is None
        else [("Eigen uitsnede", bounds)]
    )
    for _, extent in areas:
        xmin, ymin, xmax, ymax = extent
        if xmin >= xmax or ymin >= ymax:
            raise ValueError(
                "Gebruik bounds=(xmin, ymin, xmax, ymax) met oplopende grenzen."
            )

    data_store = data_store or DataStore()
    if stap >= 6:
        special_sources = special_sources or SpecialBuildingSources(
            top10nl_gpkg=data_store.top10nl_dir / "top10nl_Compleet.gpkg"
        )
        default_gemalen = data_store.source_data_dir / "hydamo" / "hydamo.gpkg"
        if gemalen_gpkg is None and default_gemalen.is_file():
            gemalen_gpkg = default_gemalen
    layers = FunctioneelLandgebruikLayers()
    bag_path = data_store.bag_dir / "bag-light.gpkg"
    output_dir = data_store.processed_data_dir / "functioneel_landgebruik" / "controle"
    filename = "bag_controle.gpkg"
    if bounds is not None:
        extent_name = "_".join(str(value).replace(".", "p") for value in bounds)
        filename = f"bag_controle_{extent_name}.gpkg"
    target = Path(target_path) if target_path is not None else output_dir / filename
    if target.exists() and not overwrite:
        validate_geopackage(target)
        print(f"Bestaand controlebestand hergebruikt: {target}")
        print("Gebruik overwrite=True om opnieuw te berekenen.")
        return target

    if not bag_path.is_file():
        raise FileNotFoundError(
            f"Bronbestand ontbreekt (geen download gestart): {bag_path}"
        )
    for layer in [layers.bag_pand, layers.bag_verblijfsobject]:
        crs = pyogrio.read_info(bag_path, layer=layer)["crs"]
        if crs is None or not same_crs(crs, settings.crs):
            raise ValueError(f"Onverwacht CRS voor {bag_path}, laag {layer}: {crs}")

    table = None
    if stap >= 5:
        table = load_landuse_table(mapping_csv or LANDGEBRUIK_CSV)
        print(f"Landgebruikcodes uit CSV: {table.path}")
    results = []
    pump_results = []
    for name, extent in areas:
        print(f"BAG lezen: {name}, uitsnede {extent}")
        bag = read_bag_source_data(
            bag_path,
            pand_layer=layers.bag_pand,
            verblijfsobject_layer=layers.bag_verblijfsobject,
            bounds=extent,
        )
        if bag.panden.empty:
            raise ValueError(
                f"Geen BAG-panden in uitsnede {name}; geen uitvoer geschreven."
            )

        area_result = _process_area(
            bag, name, stap, table=table, special_sources=special_sources
        )
        if stap >= 6 and gemalen_gpkg is not None:
            pump_bounds = _bounds_including_panden(extent, bag.panden)
            gemalen = prepare_gemalen(
                gemalen_gpkg,
                bounds=pump_bounds,
                crs=settings.crs,
                table=table,
                include_details=True,
            )
            selected = area_result.loc[area_result["meegenomen_stap2"]].copy()
            linked = link_pumping_stations(selected, gemalen, table=table)
            for column in linked.panden.columns:
                if column not in area_result:
                    area_result[column] = linked.panden[column].reindex(
                        area_result.index
                    )
                elif column != "geometry":
                    area_result.loc[selected.index, column] = linked.panden[column]
            area_result.loc[selected.index, "toelichting_resultaat"] = linked.panden[
                "reden_klasse"
            ]
            linked.gemalen["uitsnede"] = name
            pump_results.append(linked.gemalen)
        results.append(area_result)

    controle = gpd.GeoDataFrame(
        pd.concat(results, ignore_index=True), geometry="geometry", crs=results[0].crs
    )
    gemalen_controle = None
    if pump_results:
        gemalen_controle = gpd.GeoDataFrame(
            pd.concat(pump_results, ignore_index=True), crs=controle.crs
        )
    _write_control(controle, target, gemalen=gemalen_controle)

    print(f"Geschreven: {len(controle)} panden in laag bag_controle")
    print(f"Open in QGIS: {target}")
    print(f"Controle tot en met stap {stap}.")
    if stap >= 5:
        print("Beide codes getoond; binnen-/buitendijkse ligging nog niet bepaald.")
    else:
        print("Geen landgebruikscode.")
    return target


if __name__ == "__main__":
    main(overwrite=True)
