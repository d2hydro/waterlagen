"""Gemalen: punt koppelen aan een geschikt pand, dan capaciteiten optellen.

De zes capaciteitsklassen volgen de tabel in de notitie (vanaf 10 m³/min).
Onze aanvullende afspraak: gebruik BAG-geometrie bij precies één passend pand;
anders blijft het gemaal een punt. Meerdere gemalen in een pand tellen samen.
"""

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd

from waterlagen._crs import same_crs
from waterlagen.functioneel_landgebruik.landgebruikstabel import (
    LanduseTable,
    load_landuse_table,
)


def _capacity_mapping_id(capacity: float) -> str | None:
    """Dezelfde zes grenzen voor een los gemaal en de som in een pomphuis."""
    if pd.isna(capacity) or not np.isfinite(capacity) or capacity < 10:
        return None
    if capacity < 20:
        return "NGR-001"
    if capacity < 50:
        return "NGR-002"
    if capacity < 100:
        return "NGR-003"
    if capacity < 400:
        return "NGR-004"
    if capacity <= 1000:
        return "NGR-005"
    return "NGR-006"


def classify_pumping_stations(
    stations: gpd.GeoDataFrame,
    *,
    capacity_column: str = "maximalecapaciteit",
    table: LanduseTable | None = None,
) -> gpd.GeoDataFrame:
    """Assign the six agreed capacity classes, preserving unclassified records.

    Parameters
    ----------
    stations : geopandas.GeoDataFrame
        Gemaal objects. Capacity must be expressed in cubic metres per minute.
    capacity_column : str, optional
        Source capacity field. Values are not inferred from individual pumps.
    table : LanduseTable, optional
        Codes and descriptions; defaults to the packaged CSV.

    Returns
    -------
    geopandas.GeoDataFrame
        Source records with capacity, both location codes and an explanation.
        Intervals are [10,20), [20,50), [50,100), [100,400), [400,1000]
        and (1000,infinity). Missing, invalid and smaller capacities stay open.
        This classifies capacity only, not operating status or building geometry.
    """
    if capacity_column not in stations:
        raise ValueError(f"Capaciteitsveld ontbreekt: {capacity_column}")
    table = table or load_landuse_table()
    result = stations.copy()
    capacity = pd.to_numeric(result[capacity_column], errors="coerce")
    valid = capacity.notna() & np.isfinite(capacity) & (capacity >= 0)
    result["capaciteit_m3_min"] = capacity.where(valid)
    mapping_ids = result["capaciteit_m3_min"].map(_capacity_mapping_id)
    result["lgb_koppeling_id"] = pd.Series(None, index=result.index, dtype="object")
    result["lgb_omschrijving"] = pd.Series(None, index=result.index, dtype="object")
    for column in ["lgb_code_binnendijks", "lgb_code_buitendijks"]:
        result[column] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    result["reden_capaciteitsklasse"] = "Capaciteit ontbreekt of is ongeldig."
    result.loc[valid & (capacity < 10), "reden_capaciteitsklasse"] = (
        "Capaciteit onder 10 m³/min: geen gemaalklasse."
    )
    for number in range(1, 7):
        mapping_id = f"NGR-{number:03d}"
        mapping = table.by_id(mapping_id)
        selected = mapping_ids.eq(mapping_id)
        result.loc[selected, "lgb_koppeling_id"] = mapping_id
        result.loc[selected, "lgb_omschrijving"] = mapping.description
        result.loc[selected, "lgb_code_binnendijks"] = mapping.inside
        result.loc[selected, "lgb_code_buitendijks"] = mapping.outside
        result.loc[selected, "reden_capaciteitsklasse"] = (
            "Ingedeeld op broncapaciteit in m3/min; codes uit CSV."
        )
    return result


@dataclass(frozen=True)
class PumpBuildingResult:
    """Building decisions and point records with their spatial match evidence."""

    panden: gpd.GeoDataFrame
    gemalen: gpd.GeoDataFrame


def _distinct_stations(stations: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Deduplicate equal global IDs; reject ambiguous totals explicitly."""
    if stations["capaciteit_m3_min"].isna().any():
        raise ValueError("Capaciteit ontbreekt bij een gekoppeld gemaal; som onbekend.")
    if len(stations) == 1:
        return stations
    if "globalid" not in stations:
        raise ValueError(
            "Meerdere gemalen zonder globalid; dubbeltelling niet uit te sluiten."
        )
    ids = (
        stations["globalid"].astype("string").str.strip().str.strip("{}").str.casefold()
    )
    if ids.isna().any() or ids.eq("").any():
        raise ValueError(
            "Meerdere gemalen met ontbrekende globalid; dubbeltelling niet uit te sluiten."
        )
    if stations.groupby(ids)["capaciteit_m3_min"].nunique().gt(1).any():
        raise ValueError(
            "Dezelfde gemaal-globalid heeft verschillende capaciteiten; som niet bepaald."
        )
    return stations.loc[~ids.duplicated()]


def _suitable_building_reason(function_text: object) -> str | None:
    """Leg uit waarom koppelen mag; None betekent dat het gemaal punt blijft."""
    if not isinstance(function_text, str):
        return None
    functions = {part.strip() for part in function_text.split(",") if part.strip()}
    # '' = geen VBO; 'ontbreekt' = alleen lege doelen. Onbekende metadata telt niet.
    if not functions or functions == {"ontbreekt"}:
        return "Punt binnen precies een BAG-pand zonder gekoppeld VBO of met uitsluitend lege gebruiksdoelen."
    if functions.issubset({"industriefunctie", "overige gebruiksfunctie"}):
        return "Punt binnen precies een BAG-pand met uitsluitend industrie-/overige gebruiksfunctie."
    return None


def link_pumping_stations(
    panden: gpd.GeoDataFrame,
    stations: gpd.GeoDataFrame,
    *,
    table: LanduseTable | None = None,
) -> PumpBuildingResult:
    """Use BAG geometry for a unique containing pand; retain other stations as points.

    Parameters
    ----------
    panden : geopandas.GeoDataFrame
        Status-selected, classified BAG buildings. Unique index required.
    stations : geopandas.GeoDataFrame
        Points classified by ``classify_pumping_stations``, in the same CRS.
    table : LanduseTable, optional
        Editable CSV codes and descriptions.

    Returns
    -------
    PumpBuildingResult
        Panden with gemaal overrides and source points with match explanations.
        Boundary points, residential/other known uses and ambiguous matches remain
        points. Industry/other use and explicitly absent uses are linked.
        Partially missing or unknown uses remain points. Capacities of distinct gemaal
        IDs in one pand are summed before classifying; identical IDs count once.
        Missing capacities prevent aggregation. A conflict with another special
        building use remains unresolved, irrespective of record order.
    """
    if (
        panden.crs is None
        or stations.crs is None
        or not same_crs(panden.crs, stations.crs)
    ):
        raise ValueError("BAG en gemalen moeten hetzelfde CRS hebben.")
    if not panden.index.is_unique or not stations.index.is_unique:
        raise ValueError("BAG- en gemaalindices moeten uniek zijn.")
    table = table or load_landuse_table()
    buildings = panden.copy()
    points = stations.copy()
    points["bag_pand_id"] = ""
    points["bag_gebruiksdoelen"] = ""
    points["pand_capaciteit_m3_min"] = float("nan")
    points["pand_lgb_koppeling_id"] = ""
    points["geometrie_kaart"] = "punt"
    points["reden_ruimtelijke_koppeling"] = (
        "Geen BAG-pand waarin het punt ligt; punt behouden."
    )
    buildings["gekoppelde_gemalen"] = ""
    buildings["gemaalcapaciteit_m3_min"] = float("nan")
    # 1. Ruimtelijk koppelen: strikt binnen één pand, nooit naar het dichtstbijzijnde.
    matches = gpd.sjoin(
        points[["geometry"]], buildings[["geometry"]], predicate="within"
    )
    counts = matches.groupby(level=0).size()
    points["aantal_bag_panden"] = counts.reindex(points.index, fill_value=0)
    multiple = points["aantal_bag_panden"] > 1
    points.loc[multiple, "reden_ruimtelijke_koppeling"] = (
        "Punt ligt in meerdere BAG-panden; geen pand gekozen, punt behouden."
    )
    unique = matches.loc[matches.index.map(counts) == 1]
    for pand_index, group in unique.groupby("index_right"):
        station_indices = group.index
        points.loc[station_indices, "bag_pand_id"] = str(
            buildings.loc[pand_index, "identificatie"]
        )
        function_text = buildings.loc[pand_index].get("alle_bag_gebruiksdoelen", pd.NA)
        points.loc[station_indices, "bag_gebruiksdoelen"] = function_text
        # 2. Controleer alle BAG-doelen; een woonfunctie mag niet worden verborgen.
        reason = _suitable_building_reason(function_text)
        if reason is None:
            points.loc[station_indices, "reden_ruimtelijke_koppeling"] = (
                "Pandfunctie onbekend, deels ontbrekend of niet geschikt voor automatische gemaalkoppeling: "
                + (str(function_text) or "geen gebruiksdoel")
                + ". BAG-klasse behouden; gemaal blijft punt."
            )
            continue
        points.loc[station_indices, "reden_ruimtelijke_koppeling"] = reason
        # 3. Tel afzonderlijke gemalen op; dubbele of ontbrekende gegevens beoordelen.
        try:
            distinct = _distinct_stations(points.loc[station_indices])
        except ValueError as error:
            points.loc[station_indices, "reden_ruimtelijke_koppeling"] += (
                " " + str(error) + " Punten behouden."
            )
            continue
        capacity = float(distinct["capaciteit_m3_min"].sum())
        mapping_id = _capacity_mapping_id(capacity)
        points.loc[station_indices, "pand_capaciteit_m3_min"] = capacity
        if mapping_id is None:
            points.loc[station_indices, "reden_ruimtelijke_koppeling"] += (
                " Totale capaciteit buiten de zes klassen; geen pandklasse toegekend."
            )
            continue
        points.loc[station_indices, "pand_lgb_koppeling_id"] = mapping_id
        points.loc[station_indices, "geometrie_kaart"] = "BAG-pand"
        points.loc[station_indices, "reden_ruimtelijke_koppeling"] += (
            " Pandklasse op som van capaciteiten; gelijke globalid eenmaal geteld."
        )
        source_ids = (
            distinct["globalid"]
            if "globalid" in distinct
            else distinct.index.to_series()
        )
        buildings.loc[pand_index, "gekoppelde_gemalen"] = "; ".join(
            source_ids.astype(str)
        )
        buildings.loc[pand_index, "gemaalcapaciteit_m3_min"] = capacity
        # 4. Geen automatische voorrang tussen gemaal, kas, RWZI of drinkwater.
        special = buildings.loc[pand_index].get("bijzondere_koppelingen", "")
        if pd.notna(special) and special != "":
            for column in [
                "lgb_koppeling_id",
                "lgb_omschrijving",
                "lgb_code_binnendijks",
                "lgb_code_buitendijks",
            ]:
                buildings.loc[pand_index, column] = pd.NA
            buildings.loc[pand_index, "klasse_status"] = "nog te beoordelen"
            buildings.loc[pand_index, "reden_klasse"] = (
                "Gemaal en andere gebouwfunctie: voorrang nog te bepalen."
            )
            points.loc[station_indices, "reden_ruimtelijke_koppeling"] += (
                " Conflict in pand; geen definitieve pandklasse."
            )
            continue
        # 5. Pas de CSV-klasse toe op het hele pand; bewaar de bronpunten als bewijs.
        mapping = table.by_id(mapping_id)
        buildings.loc[pand_index, "lgb_koppeling_id"] = mapping_id
        buildings.loc[pand_index, "lgb_omschrijving"] = mapping.description
        buildings.loc[pand_index, "lgb_code_binnendijks"] = mapping.inside
        buildings.loc[pand_index, "lgb_code_buitendijks"] = mapping.outside
        buildings.loc[pand_index, "klasse_status"] = "ingedeeld"
        buildings.loc[pand_index, "reden_klasse"] = (
            reason
            + " Klasse op som van capaciteiten in m3/min (gelijke globalid eenmaal), BAG-geometrie behouden."
        )
    return PumpBuildingResult(buildings, points)
