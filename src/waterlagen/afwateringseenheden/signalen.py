"""Select BGT boundary-crossing culverts after checks against the primary network."""

from itertools import pairwise
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import get_parts, line_merge, union_all
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

from waterlagen._crs import same_crs
from waterlagen._downloads import _temporary_path, validate_geopackage
from waterlagen._geopackage import write_geopackage_layer
from waterlagen._geopandas import read_file
from waterlagen.logger import get_logger
from waterlagen.settings import settings

from ._signaalverbindingen import exclude_existing_connections

logger = get_logger(__name__)
BGT_SOURCE = Path("berekening") / "signaalkaart" / "bgt_duikers.gpkg"
LINE_LAYER = "duikers_afwateringsgrens"
POLYGON_LAYER = "duikervlakken_afwateringsgrens"


def _validate_geometry(features: gpd.GeoDataFrame, name: str) -> None:
    if features.crs is None or not same_crs(features.crs, settings.crs):
        raise ValueError(f"Signaalkaart: afwijkend of ontbrekend CRS voor {name}")
    if (
        features.geometry.isna().any()
        or (~features.is_valid).any()
        or features.is_empty.any()
    ):
        raise ValueError(f"Signaalkaart: ongeldige of lege geometrie in {name}")


def _read_bgt_culverts(source: Path) -> gpd.GeoDataFrame:
    if not source.is_file():
        raise FileNotFoundError(f"BGT-duikerbron voor signaalkaart ontbreekt: {source}")
    features = read_file(source, layer="bgt_duiker")
    for column, value in (("plus-type", "duiker"), ("bgt-status", "bestaand")):
        if column in features:
            features = features.loc[features[column].eq(value)]
    for column in ("eindRegistratie", "objectEindTijd"):
        if column in features:
            features = features.loc[features[column].isna()]
    _validate_geometry(features, "BGT-duikers")
    if not features.geom_type.isin(
        ["LineString", "MultiLineString", "Polygon", "MultiPolygon"]
    ).all():
        raise ValueError("Signaalkaart: BGT-duikers moeten lijnen of vlakken zijn")
    if "gml_id" not in features:
        raise ValueError("Signaalkaart: gml_id ontbreekt in de BGT-duikerbron")
    identifiers = features.gml_id.reset_index(drop=True)
    if identifiers.isna().any() or identifiers.astype(str).str.strip().eq("").any():
        raise ValueError("Signaalkaart: lege gml_id in de BGT-duikerbron")
    holders = features.get(
        "bronhouder", pd.Series(index=features.index, dtype="string")
    ).reset_index(drop=True)
    return gpd.GeoDataFrame(
        {"id": identifiers, "bronhouder": holders},
        geometry=features.geometry.reset_index(drop=True),
        crs=features.crs,
    )


def _parts(geometry: BaseGeometry, kind: str) -> list[BaseGeometry]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == kind:
        return [geometry]
    result = []
    if hasattr(geometry, "geoms"):
        for part in get_parts(geometry):
            result.extend(_parts(part, kind))
    return result


def _line_crosses_boundary(line: LineString, areas: gpd.GeoDataFrame) -> bool:
    """Require distinct endpoint areas and a real transition across a shared boundary."""
    start_areas = areas.loc[areas.contains(Point(line.coords[0])), "segment_key"]
    end_areas = areas.loc[areas.contains(Point(line.coords[-1])), "segment_key"]
    if len(start_areas) != 1 or len(end_areas) != 1:
        return False
    if start_areas.iloc[0] == end_areas.iloc[0]:
        return False
    boundary = union_all(areas.geometry.boundary)
    intervals = []
    # Split each original edge; this also handles self-crossing culvert lines.
    for start, end in pairwise(line.coords):
        edge = LineString([start, end])
        if edge.length == 0:
            continue
        contacts = edge.intersection(boundary)
        cuts = {0.0, edge.length}
        for point in _parts(contacts, "Point"):
            cuts.add(edge.project(point))
        for overlap in _parts(contacts, "LineString"):
            cuts.add(edge.project(Point(overlap.coords[0])))
            cuts.add(edge.project(Point(overlap.coords[-1])))
        for left, right in pairwise(sorted(cuts)):
            middle = edge.interpolate((left + right) / 2)
            inside = areas.loc[areas.contains(middle), "segment_key"]
            key = str(inside.iloc[0]) if len(inside) == 1 else None
            intervals.append(key)
    for previous, current in pairwise(intervals):
        if previous is not None and current is not None and previous != current:
            return True
    return False


def _crosses_boundary(geometry: BaseGeometry, areas: gpd.GeoDataFrame) -> bool:
    if geometry.geom_type in {"LineString", "MultiLineString"}:
        line = line_merge(geometry)
        # Disconnected or branching parts have no single start and end.
        if line.geom_type != "LineString":
            return False
        return _line_crosses_boundary(line, areas)
    # A polygon must have area on both sides of a shared boundary.
    candidates = areas.loc[areas.intersection(geometry).area > 0]
    for position, first in enumerate(candidates.itertuples()):
        for second in candidates.iloc[position + 1 :].itertuples():
            shared = first.geometry.boundary.intersection(second.geometry.boundary)
            interior = shared.intersection(geometry).difference(geometry.boundary)
            if interior.length > 0:
                return True
    return False


def _select_crossing_culverts(
    culverts: gpd.GeoDataFrame, areas: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    selected = []
    logger.info("Controleren van %s BGT-duikers op afwateringsgrenzen", len(culverts))
    for position, geometry in enumerate(culverts.geometry):
        nearby = areas.iloc[areas.sindex.query(geometry, predicate="intersects")]
        if _crosses_boundary(geometry, nearby):
            selected.append(position)
        if (position + 1) % 1000 == 0:
            logger.info(
                "Afwateringsgrenzen gecontroleerd: %s/%s", position + 1, len(culverts)
            )
    return culverts.iloc[selected].copy()


def _write_signals(signals: gpd.GeoDataFrame, target: Path) -> None:
    """Replace the derived map atomically, omitting empty polygon layers."""
    polygons = signals.geom_type.isin(["Polygon", "MultiPolygon"])
    layers = {}
    if (~polygons).any() or signals.empty:
        layers[LINE_LAYER] = signals.loc[~polygons]
    if polygons.any():
        layers[POLYGON_LAYER] = signals.loc[polygons]
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(target, suffix=".gpkg")
    temporary.unlink(missing_ok=True)
    try:
        for index, (name, features) in enumerate(layers.items()):
            mode = "w" if index == 0 else "a"
            write_geopackage_layer(features, temporary, layer_name=name, mode=mode)
        validate_geopackage(temporary)
        for name, features in layers.items():
            written = read_file(temporary, layer=name)
            if (
                len(written) != len(features)
                or list(written.columns) != ["id", "bronhouder", "geometry"]
                or not same_crs(written.crs, settings.crs)
            ):
                raise ValueError(f"Signaalkaartvalidatie mislukt voor {name}")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def write_duiker_signaalkaart(
    run_dir: Path,
    *,
    output_path: Path | None = None,
    bgt_duikers_path: Path | None = None,
) -> Path:
    """Write BGT boundary-crossing signals after checks against the primary network.

    Parameters
    ----------
    run_dir : pathlib.Path
        Production directory containing final ``afwateringseenheden.gpkg``,
        ``brandlagen.gpkg`` with original primary waterlines, and
        ``watersysteem.gpkg`` with primary segments and their recorded connections.
    output_path : pathlib.Path, optional
        Defaults to ``run_dir/signaalkaart.gpkg``. The entire derived file is
        replaced atomically, including any earlier assessment fields or archives.
    bgt_duikers_path : pathlib.Path, optional
        Prepared GeoPackage with layer ``bgt_duiker``. Defaults to
        ``run_dir/berekening/signaalkaart/bgt_duikers.gpkg``.

    Returns
    -------
    pathlib.Path
        Signal map with source ``gml_id`` as ``id``, ``bronhouder`` code and original
        geometry. Missing source-holder values remain null; they are not inferred
        from the identifier, which may refer to a different original holder.
        Lines and polygons have separate layers; empty polygon layers are omitted.

    Notes
    -----
    All current BGT culverts are considered independently of burn-layer selection.
    Culverts with at least 50% of their length (lines) or area (polygons) inside
    the 2 m buffer of used connected watercourses and applied connected culverts
    are excluded first. Unconnected source objects do not qualify.
    Source objects are matched through ``bron_id`` from primary target segments
    present in the final drainage areas. Their complete original geometry is used;
    overlapping buffers count once. Missing source IDs prevent primary exclusions.
    Lines must start and end strictly inside different drainage areas and cross
    a shared boundary. Disconnected lines and ambiguous endpoints are excluded.
    A route excludes a remaining line only when each endpoint is within 2 m of
    a used original primary watercourse and their targets have a recorded
    connection, irrespective of direction. Route length is
    irrelevant; confluences and splits are allowed. Merely reaching a primary
    target does not prove local attachment. Raster flow is not used for this check.
    Polygons must cross a shared boundary. For each positive-area overlap, use
    its point nearest the target segment. Route-based exclusion requires all
    these points locally attached and a recorded connection for every pair
    of targets, including the outermost pair. Original geometry is retained.
    No downloads or terrain calculations are performed.
    """
    run_dir = Path(run_dir)
    target = Path(output_path or run_dir / "signaalkaart.gpkg")
    source = Path(bgt_duikers_path or run_dir / BGT_SOURCE)

    culverts = _read_bgt_culverts(source)

    areas = read_file(
        run_dir / "afwateringseenheden.gpkg", layer="afvoergebiedaanvoergebied"
    )
    _validate_geometry(areas, "afwateringseenheden")
    if areas.segment_key.isna().any():
        raise ValueError("Afwateringseenheden zonder segment_key")
    areas = areas[["segment_key", "geometry"]].dissolve(
        by="segment_key", as_index=False
    )
    signals = _select_crossing_culverts(culverts, areas)
    signals = exclude_existing_connections(signals, run_dir, areas=areas)

    _write_signals(signals, target)
    logger.info("BGT-signaalkaart geschreven: %s (%s duikers)", target, len(signals))
    return target
