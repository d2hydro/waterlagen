"""Match culverts to existing primary routes without creating network nodes."""

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math

import geopandas as gpd
import pandas as pd
from shapely import force_2d, line_merge
from shapely.geometry import LineString, MultiLineString, Point, box
from shapely.ops import substring
from waterlagen.logger import get_logger

from .lines import _ensure_bron_id, _prepare_hydroobjecten, _to_project_crs

CULVERT_POLICY = "projected_monotone_routes_geometry_score_v1"
logger = get_logger(__name__)
_EPSILON = 1e-8
_MAX_ROUTES = 128
_MAX_VISITS = 10000


@dataclass(frozen=True)
class _Edge:
    line: int
    start: float
    end: float
    geometry: LineString
    first: tuple
    last: tuple


@dataclass(frozen=True)
class _Match:
    edges: tuple[_Edge, ...] = ()
    reason: str | None = None
    start_distance: float | None = None
    end_distance: float | None = None


@dataclass(frozen=True)
class _CulvertPreparation:
    primary: gpd.GeoDataFrame
    pieces: gpd.GeoDataFrame
    controls: gpd.GeoDataFrame
    signature: str


def _validate_culvert_options(tolerance: float, adjacent_length: float | None) -> None:
    for name, value in (
        ("duiker_tolerance", tolerance),
        ("max_aansluitlengte", adjacent_length),
    ):
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError(f"{name} must be finite and non-negative")


def _frame_identity(features: gpd.GeoDataFrame) -> str:
    """Hash selected attributes and geometry, including control-only changes."""
    digest = hashlib.sha256(str(features.crs).encode())
    digest.update(
        json.dumps(features.attrs.get("source_identity"), sort_keys=True).encode()
    )
    columns = sorted(features.columns)
    digest.update(json.dumps(columns).encode())
    for index, row in features.iterrows():
        values = [str(index)]
        for column in columns:
            value = row[column]
            if column == features.geometry.name:
                values.append(value.wkb_hex if not pd.isna(value) else None)
            else:
                values.append(None if pd.isna(value) else str(value))
        digest.update(json.dumps(values, ensure_ascii=True).encode())
    return digest.hexdigest()


def _edge(line: int, geometry: LineString, start: float, end: float) -> _Edge:
    part = substring(geometry, start, end)
    first = tuple(geometry.coords[0]) if start == 0 else ("cut", line, start)
    last = tuple(geometry.coords[-1]) if end == geometry.length else ("cut", line, end)
    return _Edge(line, start, end, part, first, last)


def _usable_line(geometry) -> LineString | None:
    if pd.isna(geometry) or geometry.is_empty or not geometry.is_valid:
        return None
    geometry = force_2d(geometry)
    if isinstance(geometry, MultiLineString):
        geometry = line_merge(geometry)
    if (
        not isinstance(geometry, LineString)
        or not geometry.is_simple
        or geometry.length == 0
    ):
        return None
    if geometry.is_ring:
        return None
    return geometry


def _candidates(
    point: Point, lines: gpd.GeoDataFrame, tolerance: float
) -> list[tuple[int, float, float]]:
    # A rectangle avoids the polygonal approximation of a circular buffer at
    # the inclusive tolerance boundary. The actual comparison is Euclidean.
    query = (
        box(
            point.x - tolerance,
            point.y - tolerance,
            point.x + tolerance,
            point.y + tolerance,
        )
        if tolerance
        else point
    )
    candidates = []
    for position in lines.sindex.query(query):
        line = lines.geometry.iloc[position]
        distance = point.distance(line)
        if distance <= tolerance:
            candidates.append((int(position), line.project(point), distance))
    return candidates


def _match_culvert(
    geometry: LineString,
    lines: gpd.GeoDataFrame,
    adjacency: dict[tuple, list[_Edge]],
    tolerance: float,
) -> _Match:
    starts = _candidates(Point(geometry.coords[0]), lines, tolerance)
    ends = _candidates(Point(geometry.coords[-1]), lines, tolerance)
    start_distance = min((item[2] for item in starts), default=None)
    end_distance = min((item[2] for item in ends), default=None)

    def failed(reason: str) -> _Match:
        return _Match(
            reason=reason, start_distance=start_distance, end_distance=end_distance
        )

    if not starts and not ends:
        return failed("geen primair hydroobject binnen tolerantie")
    if not starts or not ends:
        return failed("slechts één uiteinde binnen tolerantie")

    cuts: dict[int, set[float]] = defaultdict(set)
    for line, position, _ in (*starts, *ends):
        cuts[line].add(position)
    local: dict[tuple, list[_Edge]] = defaultdict(list)
    for line, positions in cuts.items():
        original = lines.geometry.iloc[line]
        positions = sorted({0.0, original.length, *positions})
        for start, end in zip(positions, positions[1:]):
            if end - start <= _EPSILON:
                continue
            edge = _edge(line, original, start, end)
            local[edge.first].append(edge)
            local[edge.last].append(edge)

    def node(line: int, position: float) -> tuple:
        original = lines.geometry.iloc[line]
        if position == 0:
            return tuple(original.coords[0])
        if position == original.length:
            return tuple(original.coords[-1])
        return ("cut", line, position)

    destinations = {node(line, position) for line, position, _ in ends}
    stack = [(node(line, position), (), frozenset()) for line, position, _ in starts]
    routes: dict[tuple, tuple[_Edge, ...]] = {}
    visits = 0
    while stack:
        current, route, visited = stack.pop()
        visits += 1
        if visits > _MAX_VISITS or len(routes) > _MAX_ROUTES:
            return failed("meerdere kandidaattrajecten; zoeklimiet bereikt")
        if current in destinations and route:
            key = tuple((edge.line, edge.start, edge.end) for edge in route)
            routes[key] = route
            continue
        edges = [edge for edge in adjacency.get(current, ()) if edge.line not in cuts]
        edges.extend(local.get(current, ()))
        for edge in edges:
            forward = edge.first == current
            following = edge.last if forward else edge.first
            if following in visited:
                continue
            coordinates = list(edge.geometry.coords)
            if not forward:
                coordinates.reverse()
            positions = [
                geometry.project(Point(coordinate)) for coordinate in coordinates
            ]
            # A route must advance along the supplied culvert. No corridor
            # buffer, authority preference or shortest-network-path rule is used.
            if positions[-1] <= positions[0] + _EPSILON:
                continue
            if any(
                second + _EPSILON < first
                for first, second in zip(positions, positions[1:])
            ):
                continue
            stack.append((following, (*route, edge), visited | {current}))
    if not routes:
        return failed("geen eenduidig aaneengesloten traject")
    scored = []
    for route in routes.values():
        route_geometry = MultiLineString([edge.geometry for edge in route])
        scored.append((geometry.hausdorff_distance(route_geometry), route))
    scored.sort(key=lambda item: item[0])
    if len(scored) > 1 and math.isclose(scored[0][0], scored[1][0], abs_tol=_EPSILON):
        return failed("meerdere niet eenduidig te onderscheiden kandidaattrajecten")
    return _Match(
        scored[0][1], start_distance=start_distance, end_distance=end_distance
    )


def _prepare_culverts(
    primary: gpd.GeoDataFrame,
    culverts: gpd.GeoDataFrame,
    *,
    tolerance: float,
) -> _CulvertPreparation:
    primary = _prepare_hydroobjecten(primary)
    culverts = _ensure_bron_id(_to_project_crs(culverts, name="duikersifonhevel"))
    for column, default in (("bronbestand", None), ("bronlaag", "duikersifonhevel")):
        if column not in culverts:
            culverts[column] = default
    if "bron_fid" not in culverts:
        culverts["bron_fid"] = culverts.index
    logger.info(
        "Matching %s culverts against %s full primary lines",
        len(culverts),
        len(primary),
    )
    adjacency: dict[tuple, list[_Edge]] = defaultdict(list)
    for position, geometry in enumerate(primary.geometry):
        edge = _edge(position, geometry, 0, geometry.length)
        adjacency[edge.first].append(edge)
        adjacency[edge.last].append(edge)
    intervals: dict[int, list[tuple[float, float, str]]] = defaultdict(list)
    controls = []
    for _, culvert in culverts.iterrows():
        geometry = _usable_line(culvert.geometry)
        match = (
            _match_culvert(geometry, primary, adjacency, tolerance)
            if geometry is not None
            else _Match(reason="geometrie zonder bruikbare uiteinden")
        )
        if match.reason is not None:
            control = culvert.to_dict()
            control.update(
                reden=match.reason,
                afstand_begin=match.start_distance,
                afstand_eind=match.end_distance,
            )
            controls.append(control)
            continue
        for edge in match.edges:
            intervals[edge.line].append((edge.start, edge.end, str(culvert.bron_id)))

    records = []
    for position, (_, row) in enumerate(primary.iterrows()):
        line = row.geometry
        covered = intervals[position]
        boundaries = sorted(
            {
                0.0,
                line.length,
                *(value for start, end, _ in covered for value in (start, end)),
            }
        )
        for start, end in zip(boundaries, boundaries[1:]):
            if end - start <= _EPSILON:
                continue
            middle = (start + end) / 2
            ids = sorted(
                {
                    identifier
                    for first, last, identifier in covered
                    if first <= middle <= last
                }
            )
            record = row.to_dict()
            record.update(
                geometry=substring(line, start, end),
                brandgeschikt=not ids,
                doelgeschikt=not ids,
                duiker_ids=json.dumps(ids),
                duiker_knip_start=start != 0,
                duiker_knip_eind=end != line.length,
            )
            records.append(record)
    pieces = (
        gpd.GeoDataFrame(records, geometry="geometry", crs=primary.crs)
        if records
        else primary.iloc[:0].copy()
    )
    if not records:
        for column in (
            "brandgeschikt",
            "doelgeschikt",
            "duiker_knip_start",
            "duiker_knip_eind",
        ):
            pieces[column] = pd.Series(dtype=bool)
        pieces["duiker_ids"] = pd.Series(dtype=str)
    control_frame = (
        gpd.GeoDataFrame(controls, geometry="geometry", crs=primary.crs)
        if controls
        else culverts.iloc[:0].copy()
    )
    for column in ("reden", "afstand_begin", "afstand_eind"):
        if column not in control_frame:
            control_frame[column] = pd.Series(dtype=str if column == "reden" else float)
    signature = hashlib.sha256(
        json.dumps(
            {
                "policy": CULVERT_POLICY,
                "primary": _frame_identity(primary),
                "culverts": _frame_identity(culverts),
                "tolerance": tolerance,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    logger.info(
        "Prepared %s primary pieces; %s matched culverts and %s inspection objects",
        len(pieces),
        len(culverts) - len(control_frame),
        len(control_frame),
    )
    return _CulvertPreparation(primary, pieces, control_frame, signature)


def _classify_adjacent(
    pieces: gpd.GeoDataFrame, max_length: float | None
) -> gpd.GeoDataFrame:
    """Classify direct physical pieces before general length segmentation."""
    result = pieces.copy()
    ends: dict[tuple, list[tuple[str, bool, list[str]]]] = defaultdict(list)
    for row in result.loc[~result.brandgeschikt].itertuples():
        for coordinate, cut in (
            (row.geometry.coords[0], row.duiker_knip_start),
            (row.geometry.coords[-1], row.duiker_knip_eind),
        ):
            ends[tuple(coordinate)].append(
                (row.bron_id, cut, json.loads(row.duiker_ids))
            )
    identifiers = []
    for index, row in result.iterrows():
        adjacent = set()
        if row.brandgeschikt:
            for coordinate in (row.geometry.coords[0], row.geometry.coords[-1]):
                for source, cut, culverts in ends.get(tuple(coordinate), ()):
                    if not cut or source == row.bron_id:
                        adjacent.update(culverts)
        identifiers.append(json.dumps(sorted(adjacent)))
        if adjacent and max_length is not None and row.geometry.length <= max_length:
            result.loc[index, "doelgeschikt"] = False
    result["aansluit_duiker_ids"] = identifiers
    return result
