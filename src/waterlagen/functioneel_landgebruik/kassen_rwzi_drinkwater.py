"""Stap 6: kassen, RWZI en drinkwater herkennen na de gewone BAG-indeling.

De memo (bijlage D) verwijst voor kassen naar de volledige TOP10NL-bronwaarde.
De notitie van 17 september 2025 beschrijft kassen en RWZI's op p. 6 en
drinkwater op p. 7. De BAG-geometrie blijft steeds behouden.

Onze ruimtelijke uitwerking: meer dan 50% kasoverlap; bij terreinen moet een
punt binnen het pand op het terrein liggen. Deze drempel en puntmethode zijn
geen voorschriften uit de notitie. RWZI en drinkwater blijven optioneel.
"""

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

from waterlagen import _geopandas as wgpd
from waterlagen._crs import same_crs
from waterlagen.functioneel_landgebruik.landgebruikstabel import (
    LanduseTable,
    load_landuse_table,
)
from waterlagen.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SpecialBuildingSources:
    """Sources for step 6; optional sites are never downloaded implicitly.

    RWZI records from DAMO confirm TOP10NL treatment sites by intersection.
    The legacy status fields are retained for compatibility and are ignored.
    Drinking-water input must contain verified production-site polygons.
    """

    top10nl_gpkg: Path
    greenhouse_layer: str = "top10nl_gebouw_vlak"
    rwzi_gpkg: Path | None = None
    rwzi_layer: str = "rwzi"
    rwzi_status_column: str = "status"
    rwzi_active_value: str = "in gebruik"
    drinking_water_gpkg: Path | None = None
    drinking_water_layer: str = "drinkwaterproductieterrein"


def _read_layer(
    path: Path, layer: str, *, bounds: tuple, crs, columns: list[str] | None = None
) -> gpd.GeoDataFrame:
    """Check the CRS before applying a spatial filter."""
    source_crs = pyogrio.read_info(path, layer=layer)["crs"]
    if source_crs is None or crs is None or not same_crs(source_crs, crs):
        raise ValueError(
            f"CRS komt niet overeen voor {path}, laag {layer}: {source_crs}"
        )
    return wgpd.read_file(path, layer=layer, bbox=bounds, columns=columns)


def _contains_source_value(values: pd.Series, expected: str) -> pd.Series:
    """Match full TOP10NL values, including pipe-separated multiple values."""
    selected = []
    for value in values.fillna("").astype(str):
        source_values = {part.strip().casefold() for part in value.split("|")}
        selected.append(expected in source_values)
    return pd.Series(selected, index=values.index, dtype=bool)


def _polygons_with_source_ids(polygons: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep geometry and a source ID for the explanation in the control layer."""
    if not polygons.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("Gebouw- en terreinbegrenzingen moeten polygonen zijn.")
    targets = polygons[["geometry"]].reset_index(drop=True)
    if "lokaalid" in polygons:
        targets["bron_id"] = polygons["lokaalid"].astype(str).to_numpy()
    else:
        targets["bron_id"] = targets.index.astype(str)
    return targets


def _source_ids_per_pand(matches: gpd.GeoDataFrame) -> pd.Series:
    """Summarize all matching source IDs, keeping the BAG row index."""
    return matches.groupby(level=0)["bron_id"].agg(
        lambda values: "; ".join(sorted(set(values)))
    )


def _match_greenhouses(
    panden: gpd.GeoDataFrame, greenhouses: gpd.GeoDataFrame
) -> pd.Series:
    """Notitie p. 6: gebruik BAG-panden; onze grens is meer dan 50% kasoverlap."""
    if greenhouses.empty:
        return pd.Series(dtype="object")
    targets = _polygons_with_source_ids(greenhouses)
    matches = gpd.sjoin(panden[["geometry"]], targets, predicate="intersects")
    retained = []
    for pand_index, group in matches.groupby(level=0):
        pand_geometry = panden.loc[pand_index].geometry
        # Eerst samenvoegen: overlappende kasvlakken tellen niet dubbel mee.
        greenhouse_geometry = targets.loc[
            group["index_right"].unique()
        ].geometry.union_all()
        overlap_area = pand_geometry.intersection(greenhouse_geometry).area
        if pand_geometry.area > 0 and overlap_area > pand_geometry.area / 2:
            retained.append(pand_index)
    return _source_ids_per_pand(matches.loc[matches.index.isin(retained)])


def _match_site_buildings(
    panden: gpd.GeoDataFrame, sites: gpd.GeoDataFrame
) -> pd.Series:
    """Selecteer panden waarvan een intern punt binnen het terrein ligt."""
    if sites.empty:
        return pd.Series(dtype="object")
    targets = _polygons_with_source_ids(sites)
    pand_points = panden[["geometry"]].copy()
    pand_points.geometry = pand_points.geometry.representative_point()
    matches = gpd.sjoin(pand_points, targets, predicate="within")
    return _source_ids_per_pand(matches)


def _damo_rwzi_sites(
    sources: SpecialBuildingSources, *, bounds: tuple, crs
) -> gpd.GeoDataFrame:
    """Keep complete TOP10NL treatment polygons intersecting DAMO RWZI features."""
    data = _read_layer(
        sources.top10nl_gpkg, "top10nl_functioneel_gebied_vlak", bounds=bounds, crs=crs
    )
    sites = data.loc[data["typefunctioneelgebied"].eq("zuiveringsinstallatie"),].copy()
    if sites.empty:
        return sites
    # Validate polygon geometry and retain source IDs where available.
    sites = _polygons_with_source_ids(sites).rename(columns={"bron_id": "lokaalid"})
    # The confirming DAMO feature may be outside the building/tile extent.
    records = _read_layer(
        sources.rwzi_gpkg, sources.rwzi_layer, bounds=tuple(sites.total_bounds), crs=crs
    )
    matches = gpd.sjoin(sites, records[["geometry"]], predicate="intersects")
    validated = sites.loc[sites.index.isin(matches.index)]
    logger.info(
        "RWZI-terreinen: %s van %s bevestigd door DAMO", len(validated), len(sites)
    )
    return validated


def apply_special_building_classes(
    panden: gpd.GeoDataFrame,
    sources: SpecialBuildingSources,
    *,
    table: LanduseTable | None = None,
) -> gpd.GeoDataFrame:
    """Apply step 6 after ordinary BAG classification, preserving its results.

    Parameters
    ----------
    panden : geopandas.GeoDataFrame
        Selected BAG panden after step 5, in the source CRS. Unique index required.
    sources : SpecialBuildingSources
        TOP10NL and optional DAMO RWZI and drinking-water site sources.
    table : LanduseTable, optional
        Codes and descriptions from the editable CSV.

    Returns
    -------
    geopandas.GeoDataFrame
        Same BAG geometries and rows, with base and final classifications.
        A greenhouse covers more than half the BAG footprint. For sites the
        pand's representative point must lie inside the site. These spatial
        criteria are implementation choices, not prescribed by the note.
        Conflicting special uses remain unresolved; row order never chooses one.
        Missing optional sources are logged and not interpreted as negative evidence.
    """
    if not panden.index.is_unique:
        raise ValueError("BAG-pandindex moet uniek zijn.")
    table = table or load_landuse_table()
    result = panden.copy()
    landuse_columns = [
        "lgb_koppeling_id",
        "lgb_omschrijving",
        "lgb_code_binnendijks",
        "lgb_code_buitendijks",
    ]
    # Bewaar de gewone BAG-uitkomst naast de bijzondere gebouwklasse.
    for column in landuse_columns + ["klasse_status", "reden_klasse"]:
        result[f"basis_{column}"] = result[column]
    result["bijzondere_koppelingen"] = ""
    result["bijzondere_bron_ids"] = ""
    result["controle_bijzondere_bronnen"] = (
        f"kassen: onderzocht; RWZI: {'onderzocht' if sources.rwzi_gpkg else 'bron ontbreekt'}; "
        f"drinkwater: {'onderzocht' if sources.drinking_water_gpkg else 'bron ontbreekt'}"
    )
    if result.empty:
        return result
    bounds = tuple(result.total_bounds)
    # 6a. Kassen: volledige bronwaarde, geen woordherkenning (memo bijlage D).
    buildings = _read_layer(
        sources.top10nl_gpkg, sources.greenhouse_layer, bounds=bounds, crs=result.crs
    )
    greenhouses = buildings.loc[
        _contains_source_value(buildings["typegebouw"], "kas, warenhuis")
    ]
    candidates = {"TOP10NL-BAG-001": _match_greenhouses(result, greenhouses)}
    # 6b. RWZI: TOP10NL-terreinen bevestigd door DAMO, zonder statusfilter.
    if sources.rwzi_gpkg is not None:
        sites = _damo_rwzi_sites(sources, bounds=bounds, crs=result.crs)
        candidates["TOP10NL-NGR-BAG-001"] = _match_site_buildings(result, sites)
    else:
        logger.warning(
            "RWZI-gebouwselectie overgeslagen: DAMO-waterketenbron ontbreekt"
        )
    # 6c. Drinkwater: alleen aangeleverde productieterreinen (p. 7).
    if sources.drinking_water_gpkg is not None:
        sites = _read_layer(
            sources.drinking_water_gpkg,
            sources.drinking_water_layer,
            bounds=bounds,
            crs=result.crs,
        )
        candidates["TOP10NL-BAG-002"] = _match_site_buildings(result, sites)
    else:
        logger.warning(
            "Drinkwatergebouwselectie overgeslagen: productie-terreinbegrenzingen ontbreken"
        )
    reasons = {
        "TOP10NL-BAG-001": "Meer dan 50% van BAG-pand overlapt TOP10NL kas, warenhuis; BAG-geometrie behouden.",
        "TOP10NL-NGR-BAG-001": "Representatief pandpunt ligt binnen TOP10NL-zuiveringsterrein dat een DAMO RWZI-object snijdt.",
        "TOP10NL-BAG-002": "Pandpunt ligt binnen aangeleverd drinkwaterproductieterrein.",
    }
    reasons["TOP10NL-NGR-BAG-002"] = reasons["TOP10NL-NGR-BAG-001"]
    # 6d. CSV-codes toepassen. Bij verschillende klassen blijft de keuze open.
    # Maak één overzicht per pand, in plaats van elke selectie opnieuw te zoeken.
    pand_matches = {}
    for mapping_id, matches in candidates.items():
        for index, source_ids in matches.items():
            pand_matches.setdefault(index, {})[mapping_id] = source_ids
    for index, matches in pand_matches.items():
        ids = list(matches)
        result.loc[index, "bijzondere_koppelingen"] = "; ".join(ids)
        result.loc[index, "bijzondere_bron_ids"] = "; ".join(
            f"{mapping_id}: {source_ids}" for mapping_id, source_ids in matches.items()
        )
        codes = {(table.by_id(key).inside, table.by_id(key).outside) for key in ids}
        if len(codes) > 1:
            result.loc[index, landuse_columns] = pd.NA
            result.loc[index, "klasse_status"] = "nog te beoordelen"
            result.loc[index, "reden_klasse"] = (
                "Gebouwfuncties overlappen; voorrang nog te bepalen: "
                + "; ".join(dict.fromkeys(table.by_id(key).description for key in ids))
            )
            continue
        mapping_id = ids[0]
        mapping = table.by_id(mapping_id)
        result.loc[index, "lgb_koppeling_id"] = mapping_id
        result.loc[index, "lgb_omschrijving"] = mapping.description
        result.loc[index, "lgb_code_binnendijks"] = mapping.inside
        result.loc[index, "lgb_code_buitendijks"] = mapping.outside
        result.loc[index, "klasse_status"] = "ingedeeld"
        result.loc[index, "reden_klasse"] = reasons[mapping_id]
    logger.info(
        "Bijzondere gebouwen: %s panden met een koppeling",
        int(result["bijzondere_koppelingen"].ne("").sum()),
    )
    return result
