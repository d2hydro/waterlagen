"""Exclude BGT signals using network overlap or locally attached primary routes."""

from pathlib import Path

import geopandas as gpd
from shapely import union_all
from shapely.geometry.base import BaseGeometry

from waterlagen._crs import same_crs
from waterlagen._geopandas import read_file
from waterlagen.logger import get_logger

from ._primaire_signaalverbindingen import (
    culvert_target_points,
    read_primary_routes,
)
from ._signaalnetwerk import read_used_network

logger = get_logger(__name__)
NETWORK_BUFFER_DISTANCE_M = 2.0
NETWORK_OVERLAP_FRACTION = 0.5


def _read_used_primary_waterlines(
    run_dir: Path, areas: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Use whole source objects with a primary segment represented in the final areas."""
    path = run_dir / "brandlagen.gpkg"
    if not path.is_file():
        raise FileNotFoundError(
            f"Primaire waterlopen voor signaalkaart ontbreken: {path}"
        )
    primary = read_file(path, layer="hydamo_primair")
    if primary.crs is None or not same_crs(primary.crs, areas.crs):
        raise ValueError("Signaalkaart: afwijkend CRS voor primaire waterlopen")
    if (
        primary.geometry.isna().any()
        or primary.is_empty.any()
        or (~primary.is_valid).any()
        or not primary.geom_type.isin(["LineString", "MultiLineString"]).all()
    ):
        raise ValueError("Signaalkaart: ongeldige geometrie van primaire waterlopen")
    segments = read_file(run_dir / "watersysteem.gpkg", layer="hydroobject_segment")
    targets = segments.loc[segments.segment_key.isin(areas.segment_key)]
    if primary.empty or targets.empty:
        return primary.iloc[:0]
    if "bron_id" not in primary or "bron_id" not in targets:
        logger.warning(
            "Primaire bron_id ontbreekt; duikers worden niet vrijgesteld op basis van primair"
        )
        return primary.iloc[:0]
    source_ids = targets.bron_id.dropna().unique()
    return primary.loc[primary.bron_id.isin(source_ids)]


def _overlaps_network_zone(geometry: BaseGeometry, zones: gpd.GeoDataFrame) -> bool:
    """Require at least half the line length or polygon area; count overlap once."""
    nearby = zones.iloc[zones.sindex.query(geometry, predicate="intersects")]
    if nearby.empty:
        return False
    overlap = geometry.intersection(union_all(nearby.geometry))
    if geometry.geom_type in {"Polygon", "MultiPolygon"}:
        return overlap.area >= NETWORK_OVERLAP_FRACTION * geometry.area
    return overlap.length >= NETWORK_OVERLAP_FRACTION * geometry.length


def exclude_existing_connections(
    culverts: gpd.GeoDataFrame,
    run_dir: Path,
    *,
    areas: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Check used network overlap, then locally attached line or polygon targets."""
    primary_routes = read_primary_routes(run_dir)
    primary = _read_used_primary_waterlines(run_dir, areas)
    network = read_used_network(run_dir, primary, culverts)
    network_zones = gpd.GeoDataFrame(
        geometry=network.geometry.buffer(NETWORK_BUFFER_DISTANCE_M), crs=network.crs
    )
    selected = []
    overlap_count = 0
    for position, geometry in enumerate(culverts.geometry):
        if _overlaps_network_zone(geometry, network_zones):
            overlap_count += 1
            continue
        targets = culvert_target_points(geometry, areas, primary_routes)
        if len(targets) < 2:
            selected.append(position)
            continue
        all_points_attached = all(
            len(
                primary.sindex.query(
                    point, predicate="dwithin", distance=NETWORK_BUFFER_DISTANCE_M
                )
            )
            > 0
            for point in targets.values()
        )
        excluded = all_points_attached and primary_routes.connects_all(set(targets))
        if not excluded:
            selected.append(position)
    logger.info(
        "BGT-duikers weggelaten: %s door minimaal 50%% netwerkoverlap, %s door bestaande primaire verbinding",
        overlap_count,
        len(culverts) - len(selected) - overlap_count,
    )
    return culverts.iloc[sorted(selected)].copy()
