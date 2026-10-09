"""Stap 1: lees panden en gekoppelde verblijfsobjecten uit de BAG."""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

import geopandas as gpd
import pandas as pd

from waterlagen import _geopandas as wgpd
from waterlagen.functioneel_landgebruik.bag_zoekindex import (
    ensure_bag_link_index,
    find_vbo_fids,
)


@dataclass
class BagSourceData:
    """Panden, verblijfsobjecten en een bronoverzicht per pand."""

    panden: gpd.GeoDataFrame
    verblijfsobjecten: gpd.GeoDataFrame


def _bounds_including_panden(
    bounds: tuple[float, float, float, float], panden: gpd.GeoDataFrame
) -> tuple[float, float, float, float]:
    """Neem hele panden mee, zodat gemalen buiten de tegel ook bij de som horen."""
    if panden.empty:
        return bounds
    xmin, ymin, xmax, ymax = panden.total_bounds
    return (
        min(bounds[0], xmin),
        min(bounds[1], ymin),
        max(bounds[2], xmax),
        max(bounds[3], ymax),
    )


def read_bag_source_data(
    path: Path,
    *,
    bounds: tuple[float, float, float, float],
    pand_layer: str = "pand",
    verblijfsobject_layer: str = "verblijfsobject",
) -> BagSourceData:
    """Lees een uitsnede met alle gekoppelde verblijfsobjecten.

    Parameters
    ----------
    path : pathlib.Path
        BAG-GeoPackage. Ernaast wordt een herbruikbare zoekindex opgeslagen.
    bounds : tuple of float
        Selectiegrenzen in het CRS van de bron; panden worden niet afgeknipt.
    pand_layer, verblijfsobject_layer : str
        Namen van de bronlagen.

    Returns
    -------
    BagSourceData
        - Volledige brongegevens, zonder selectie op status of gebruiksdoel.
        - Alle verblijfsobjecten per pand-ID, ook buiten de uitsnede of gedeeld.
        - ``bron_aantal_vbo`` en ``bron_vbo_overzicht`` per pand.
    """
    panden = wgpd.read_file(path, layer=pand_layer, bbox=bounds)
    ids = panden["identificatie"].dropna().astype(str).unique().tolist()
    if ids:
        index_path = ensure_bag_link_index(path, layer=verblijfsobject_layer)
        fids = find_vbo_fids(index_path, ids)
    else:
        fids = []
    if fids:
        vbo = wgpd.read_file(
            path, layer=verblijfsobject_layer, engine="pyogrio", fids=fids
        )
        vbo = vbo.drop_duplicates(subset="identificatie").copy()
    else:
        vbo = wgpd.read_file(path, layer=verblijfsobject_layer, where="1=0")

    # Behoud bronwaarden; splits alleen pand-ID's voor het overzicht.
    overview = {pand_id: [] for pand_id in ids}
    for _, row in vbo.iterrows():
        goals = (
            "ontbreekt" if pd.isna(row["gebruiksdoel"]) else str(row["gebruiksdoel"])
        )
        area = "onbekend" if pd.isna(row["oppervlakte"]) else str(row["oppervlakte"])
        text = f"{row['identificatie']}: {goals} | {area} m² (gehele verblijfsobject)"
        for pand_id in set(str(row["pand_identificatie"]).replace(" ", "").split(",")):
            if pand_id in overview:
                overview[pand_id].append(text)
    panden["bron_aantal_vbo"] = panden["identificatie"].map(
        {key: len(value) for key, value in overview.items()}
    )
    panden["bron_vbo_overzicht"] = panden["identificatie"].map(
        {
            key: "\n".join(value) if value else "Geen gekoppeld verblijfsobject in bron"
            for key, value in overview.items()
        }
    )
    return BagSourceData(panden=panden, verblijfsobjecten=vbo)


def _group_verblijfsobjecten_by_pand(
    verblijfsobjecten: gpd.GeoDataFrame,
) -> dict[str, gpd.GeoDataFrame]:
    """Groepeer unieke verblijfsobjecten per pand; behoud alle gebruiksdoelen."""
    links = verblijfsobjecten.copy()
    links["gekoppeld_pand"] = (
        links["pand_identificatie"].fillna("").astype(str).str.split(",")
    )
    links = links.explode("gekoppeld_pand")
    links["gekoppeld_pand"] = links["gekoppeld_pand"].str.strip()
    links = links.drop_duplicates(["identificatie", "gekoppeld_pand"])
    return {key: group for key, group in links.groupby("gekoppeld_pand")}


def _format_area(area: float) -> str:
    """Toon de bronoppervlakte met Nederlandse getalnotatie, zonder afronden."""
    number = float(area)
    text = f"{int(number):,}" if number.is_integer() else f"{number:,}"
    return text.translate(str.maketrans(".,", ",.")) + " m²"


def _invalid_area_reason(vbo: pd.DataFrame) -> str:
    """Noem de verblijfsobjecten waarvan de oppervlakte niet bruikbaar is."""
    areas = pd.to_numeric(vbo["oppervlakte"], errors="coerce")
    reasons = []
    for index, row in vbo.iterrows():
        area = areas.loc[index]
        if pd.notna(area) and isfinite(area) and area > 0:
            continue
        label = f"VBO {row['identificatie']} ({row['gebruiksdoel']})"
        if pd.isna(row["oppervlakte"]):
            detail = "oppervlakte ontbreekt"
        elif pd.notna(area) and isfinite(area):
            detail = f"{_format_area(area)} is ongeldig"
        else:
            detail = f"ongeldige oppervlakte '{row['oppervlakte']}'"
        reasons.append(f"{label}: {detail}.")
    return " ".join(reasons)


def _shared_area_reason(vbo: pd.DataFrame) -> str:
    """Toon welk vloeroppervlak niet over de gekoppelde panden is verdeeld."""
    shared = vbo.loc[vbo["pand_identificatie"].str.contains(",", regex=False)]
    reasons = []
    for _, row in shared.iterrows():
        area = pd.to_numeric(row["oppervlakte"], errors="coerce")
        area_text = (
            _format_area(area)
            if pd.notna(area) and isfinite(area)
            else "oppervlakte onbekend"
        )
        count = len(set(str(row["pand_identificatie"]).replace(" ", "").split(",")))
        reasons.append(
            f"VBO {row['identificatie']} ({row['gebruiksdoel']}): {area_text}, verdeling over {count} panden onbekend."
        )
    return " ".join(reasons)
