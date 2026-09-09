"""Prepare and split primary HyDAMO hydroobjecten into a watersysteem."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
import math

import geopandas as gpd
import pandas as pd
from shapely import force_2d
from shapely.geometry import LineString, MultiLineString, MultiPoint, Point
from shapely.ops import split, substring

from waterlagen._crs import same_crs
from waterlagen.logger import get_logger
from waterlagen.settings import settings

logger = get_logger(__name__)

POSITION_TOLERANCE = 1e-9


@dataclass(frozen=True)
class WatersysteemResult:
    """Prepared primary hydroobject segments and point-induced connections.

    ``hydroobject_segmenten`` contains primary source lines split at internal
    point locations and subsequently, by the workflow, at the requested maximum
    length. ``hydroobject_verbinding`` contains a directed, minimal connection
    tree between final ``segment_id`` values at each hydrological node. A
    segment ending at a node is ``van_segment`` and a segment starting there
    is ``naar_segment``. At a node with multiple incoming and
    outgoing segments, the lexicographically first segment of each direction
    is the deterministic main route. Connection geometries are always
    two-dimensional Points at a shared segment endpoint or at the puntobject
    that connects endpoints of distinct source hydroobjects.
    """

    hydroobject_segmenten: gpd.GeoDataFrame
    hydroobject_verbinding: gpd.GeoDataFrame


@dataclass(frozen=True)
class _Endpoint:
    """Represent one directed segment endpoint at a hydrological node."""

    segment_id: str
    bron_id: str
    direction: str
    geometry: Point


def _validate_tolerance(tolerance: float) -> None:
    """Validate the maximum point-to-line distance used for snapping."""
    if tolerance < 0:
        raise ValueError("tolerance must not be negative")


def _source_identifier(row: pd.Series, index: object) -> str:
    """Return the most useful non-empty source identifier for a feature."""
    for column in ("bron_id", "globalid", "code"):
        value = row.get(column)
        if value is not None and not pd.isna(value) and str(value).strip():
            return str(value)
    return str(index)


def _ensure_bron_id(features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add stable source identifiers without discarding existing attributes."""
    result = features.copy()
    result["bron_id"] = [
        _source_identifier(row, index) for index, row in result.iterrows()
    ]
    return result


def _to_project_crs(features: gpd.GeoDataFrame, *, name: str) -> gpd.GeoDataFrame:
    """Require a CRS and transform source data to the configured project CRS."""
    if features.crs is None:
        raise ValueError(f"{name} has no CRS")
    if same_crs(features.crs, settings.crs):
        return features.copy()
    logger.info("Transforming %s from %s to %s", name, features.crs, settings.crs)
    return features.to_crs(settings.crs)


def _prepare_hydroobjecten(hydroobjecten: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Transform, validate, and explode line geometry while preserving fields."""
    source = _to_project_crs(hydroobjecten, name="hydroobjecten")
    records: list[dict[str, object]] = []
    for index, row in source.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty or not geometry.is_valid:
            logger.warning(
                "Skipping invalid or empty hydroobject geometry at index %s", index
            )
            continue
        geometry = force_2d(geometry)
        if isinstance(geometry, MultiLineString):
            logger.warning("Exploding MultiLineString hydroobject at index %s", index)
            geometries: Iterable[LineString] = geometry.geoms
        elif isinstance(geometry, LineString):
            geometries = (geometry,)
        else:
            raise ValueError(
                "hydroobjecten must contain LineString or MultiLineString geometries; "
                f"index {index} has {geometry.geom_type}"
            )
        for line in geometries:
            if line.is_empty or line.length == 0:
                logger.warning("Skipping empty hydroobject line at index %s", index)
                continue
            record = row.drop(labels="geometry").to_dict()
            record["geometry"] = line
            records.append(record)

    if not records:
        result = source.iloc[0:0].copy()
    else:
        result = gpd.GeoDataFrame(records, geometry="geometry", crs=settings.crs)
    return _ensure_bron_id(result).reset_index(drop=True)


def _prepare_puntobjecten(puntobjecten: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Transform and validate point geometry while preserving relevant fields."""
    source = _to_project_crs(puntobjecten, name="puntobjecten")
    records: list[dict[str, object]] = []
    for index, row in source.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty or not geometry.is_valid:
            logger.warning(
                "Skipping invalid or empty puntobject geometry at index %s", index
            )
            continue
        geometry = force_2d(geometry)
        if not isinstance(geometry, Point):
            raise ValueError(
                "puntobjecten must contain Point geometries; "
                f"index {index} has {geometry.geom_type}"
            )
        record = row.drop(labels="geometry").to_dict()
        record.setdefault("objecttype", "puntobject")
        record["geometry"] = geometry
        records.append(record)

    if not records:
        result = source.iloc[0:0].copy()
        if "objecttype" not in result.columns:
            result["objecttype"] = pd.Series(dtype="object")
    else:
        result = gpd.GeoDataFrame(records, geometry="geometry", crs=settings.crs)
    return _ensure_bron_id(result).reset_index(drop=True)


def _empty_verbindingen() -> gpd.GeoDataFrame:
    """Return an empty connection layer with its stable public schema."""
    return gpd.GeoDataFrame(
        {
            "van_segment": pd.Series(dtype="object"),
            "naar_segment": pd.Series(dtype="object"),
            "van_bron_id": pd.Series(dtype="object"),
            "naar_bron_id": pd.Series(dtype="object"),
            "objecttype": pd.Series(dtype="object"),
            "punt_bron_id": pd.Series(dtype="object"),
            "punt_code": pd.Series(dtype="object"),
            "punt_naam": pd.Series(dtype="object"),
            "waterbeheercode": pd.Series(dtype="object"),
        },
        geometry=gpd.GeoSeries([], crs=settings.crs),
        crs=settings.crs,
    )


def _unique_internal_positions(
    positions: Iterable[float],
    *,
    line_length: float,
) -> list[float]:
    """Keep sorted, unique positions that lie strictly inside a source line."""
    unique_positions: list[float] = []
    for position in sorted(positions):
        if math.isclose(position, 0.0, abs_tol=POSITION_TOLERANCE):
            continue
        if math.isclose(position, line_length, abs_tol=POSITION_TOLERANCE):
            continue
        if unique_positions and math.isclose(
            position,
            unique_positions[-1],
            abs_tol=POSITION_TOLERANCE,
        ):
            continue
        unique_positions.append(position)
    return unique_positions


def split_hydroobjecten_at_points(
    hydroobjecten: gpd.GeoDataFrame,
    puntobjecten: gpd.GeoDataFrame,
    *,
    tolerance: float,
) -> WatersysteemResult:
    """Split hydroobjecten at nearby points and derive inter-line connections.

    A point is projected to each LineString at distance no greater than
    ``tolerance``. Internal, unique projected positions split the source line.
    Endpoint positions are intentionally not split. Connections are derived
    after the final length segmentation, because only then every connection can
    refer to final ``segment_id`` values.

    Parameters
    ----------
    hydroobjecten : geopandas.GeoDataFrame
        LineString or MultiLineString source features. Missing source IDs are
        derived safely from ``globalid``, ``code``, or the row index.
    puntobjecten : geopandas.GeoDataFrame
        Point source features. Relevant point attributes are copied to derived
        connection records.
    tolerance : float
        Maximum projected point-to-line distance in project-CRS units.

    Returns
    -------
    WatersysteemResult
        Split source lines and deterministic point-induced connections, both in
        ``settings.crs``.
    """
    _validate_tolerance(tolerance)
    lines = _prepare_hydroobjecten(hydroobjecten)
    points = _prepare_puntobjecten(puntobjecten)
    if lines.empty or points.empty:
        return WatersysteemResult(lines, _empty_verbindingen())

    line_index = lines.sindex
    events_by_line: dict[int, list[float]] = defaultdict(list)
    unmatched_points = 0
    for point_position, point in enumerate(points.geometry):
        query_geometry = point if tolerance == 0 else point.buffer(tolerance)
        candidate_positions = line_index.query(query_geometry, predicate="intersects")
        matched = False
        for line_position in candidate_positions:
            line = lines.geometry.iloc[line_position]
            distance_to_line = point.distance(line)
            if distance_to_line > tolerance:
                continue
            projected_distance = line.project(point)
            events_by_line[line_position].append(projected_distance)
            matched = True
        if not matched:
            unmatched_points += 1

    if unmatched_points:
        logger.warning(
            "Ignored %s puntobjecten outside hydroobject tolerance %s",
            unmatched_points,
            tolerance,
        )

    records: list[dict[str, object]] = []
    split_point_count = 0
    for line_position, (_, row) in enumerate(lines.iterrows()):
        line = row.geometry
        positions = _unique_internal_positions(
            events_by_line[line_position],
            line_length=line.length,
        )
        if positions:
            parts = [
                part
                for part in split(
                    line,
                    MultiPoint([line.interpolate(position) for position in positions]),
                ).geoms
                if isinstance(part, LineString)
                and not part.is_empty
                and part.length > 0
            ]
            split_point_count += len(positions)
        else:
            parts = [line]
        for part in parts:
            record = row.drop(labels="geometry").to_dict()
            record["geometry"] = part
            records.append(record)

    segmenten = gpd.GeoDataFrame(records, geometry="geometry", crs=settings.crs)
    logger.info(
        "Split %s hydroobjecten at %s point locations into %s segments",
        len(lines),
        split_point_count,
        len(segmenten),
    )
    return WatersysteemResult(segmenten, _empty_verbindingen())


def _puntattributen(puntobject: pd.Series | None) -> dict[str, object]:
    """Return stable connection attributes for an optional causing pointobject."""
    if puntobject is None:
        return {
            "objecttype": None,
            "punt_bron_id": None,
            "punt_code": None,
            "punt_naam": None,
            "waterbeheercode": None,
        }
    return {
        "objecttype": puntobject.get("objecttype"),
        "punt_bron_id": puntobject.get("bron_id"),
        "punt_code": puntobject.get("code"),
        "punt_naam": puntobject.get("naam"),
        "waterbeheercode": puntobject.get("waterbeheercode"),
    }


def _nearest_puntobject(
    connection_point: Point,
    puntobjecten: gpd.GeoDataFrame,
    point_index,
    *,
    tolerance: float,
) -> pd.Series | None:
    """Return the nearest pointobject that is within the configured tolerance."""
    if puntobjecten.empty:
        return None
    query_geometry = (
        connection_point if tolerance == 0 else connection_point.buffer(tolerance)
    )
    candidate_positions = point_index.query(query_geometry, predicate="intersects")
    candidates = [
        (connection_point.distance(puntobjecten.geometry.iloc[position]), position)
        for position in candidate_positions
        if connection_point.distance(puntobjecten.geometry.iloc[position]) <= tolerance
    ]
    if not candidates:
        return None
    _, position = min(
        candidates,
        key=lambda candidate: (
            candidate[0],
            str(puntobjecten.iloc[candidate[1]].get("bron_id")),
        ),
    )
    return puntobjecten.iloc[position]


def _directed_connection_pairs(
    endpoints: Iterable[_Endpoint],
) -> list[tuple[_Endpoint, _Endpoint]]:
    """Create a deterministic directed tree for the segments at one node.

    Each segment contributes at most one endpoint. A node with ``n`` segments
    yields exactly ``n - 1`` pairs. Where multiple incoming and outgoing
    segments meet, the lowest segment ID in each direction forms the main
    route; the other incoming segments connect to the main outgoing segment.
    When all segments have the same direction, the lowest segment ID is the
    deterministic tree root. This is a topological fallback because the source
    geometries do not provide an incoming-to-outgoing relation at that node.
    This provides stable output for hydrologically ambiguous junctions without
    creating every possible pair.
    """
    direction_order = {"incoming": 0, "outgoing": 1}
    by_segment: dict[str, _Endpoint] = {}
    for endpoint in sorted(
        endpoints,
        key=lambda endpoint: (
            endpoint.segment_id,
            direction_order[endpoint.direction],
        ),
    ):
        by_segment.setdefault(endpoint.segment_id, endpoint)

    incoming = sorted(
        (
            endpoint
            for endpoint in by_segment.values()
            if endpoint.direction == "incoming"
        ),
        key=lambda endpoint: endpoint.segment_id,
    )
    outgoing = sorted(
        (
            endpoint
            for endpoint in by_segment.values()
            if endpoint.direction == "outgoing"
        ),
        key=lambda endpoint: endpoint.segment_id,
    )
    if incoming and outgoing:
        main_incoming = incoming[0]
        main_outgoing = outgoing[0]
        return [(main_incoming, endpoint) for endpoint in outgoing] + [
            (endpoint, main_outgoing) for endpoint in incoming[1:]
        ]
    if incoming:
        main_incoming = incoming[0]
        return [(endpoint, main_incoming) for endpoint in incoming[1:]]
    if outgoing:
        main_outgoing = outgoing[0]
        return [(main_outgoing, endpoint) for endpoint in outgoing[1:]]
    return []


def create_hydroobject_verbindingen(
    hydroobject_segmenten: gpd.GeoDataFrame,
    puntobjecten: gpd.GeoDataFrame,
    *,
    tolerance: float,
) -> gpd.GeoDataFrame:
    """Create directed Point connections between final hydroobject segments.

    A segment ending at a node becomes ``van_segment``; a segment starting at
    that node becomes ``naar_segment``. Each hydrological node with
    ``n`` participating segments receives exactly ``n - 1`` connection records.
    A node with multiple incoming and multiple outgoing segments is
    hydrologically ambiguous. Its lexicographically first incoming and outgoing
    segment form a deterministic main route; every other incoming segment joins
    that outgoing segment, while the main incoming segment connects to every
    outgoing segment. If all segments have the same direction, the lowest
    segment ID is the deterministic tree root because no incoming-to-outgoing
    relation can be inferred from the source geometries.

    Shared segment endpoints always form a node. A pointobject within
    ``tolerance`` additionally forms a node for endpoints from distinct source
    hydroobjects, preserving attributes of the point that caused that
    connection. Geometric crossings without shared endpoints or a supporting
    pointobject do not create a connection. Internal line cuts and max-length
    cuts are therefore represented without creating all pairwise combinations.
    """
    _validate_tolerance(tolerance)
    segmenten = _prepare_hydroobjecten(hydroobject_segmenten)
    if "segment_id" not in segmenten.columns:
        raise ValueError("hydroobject_segmenten has no segment_id column")
    punten = _prepare_puntobjecten(puntobjecten)
    if segmenten.empty:
        return _empty_verbindingen()

    endpoint_records: list[dict[str, object]] = []
    for _, segment in segmenten.iterrows():
        line = segment.geometry
        for coordinate, direction in (
            (line.coords[0], "outgoing"),
            (line.coords[-1], "incoming"),
        ):
            endpoint_records.append(
                {
                    "segment_id": str(segment["segment_id"]),
                    "bron_id": str(segment["bron_id"]),
                    "direction": direction,
                    "geometry": Point(coordinate),
                }
            )
    endpoints = gpd.GeoDataFrame(
        endpoint_records,
        geometry="geometry",
        crs=settings.crs,
    )
    endpoint_index = endpoints.sindex
    endpoint_groups: defaultdict[bytes, list[int]] = defaultdict(list)
    for position, endpoint in enumerate(endpoints.geometry):
        endpoint_groups[endpoint.wkb].append(position)

    point_index = punten.sindex if not punten.empty else None
    records: list[dict[str, object]] = []
    connection_keys: set[tuple[str, str, bytes]] = set()

    def add_connection(
        first_endpoint: _Endpoint,
        second_endpoint: _Endpoint,
        connection_point: Point,
        puntobject: pd.Series | None,
    ) -> None:
        first_segment = first_endpoint.segment_id
        second_segment = second_endpoint.segment_id
        if first_segment == second_segment:
            return
        connection_key = (
            first_segment,
            second_segment,
            connection_point.wkb,
        )
        if connection_key in connection_keys:
            return
        connection_keys.add(connection_key)
        record = {
            "van_segment": first_segment,
            "naar_segment": second_segment,
            "van_bron_id": first_endpoint.bron_id,
            "naar_bron_id": second_endpoint.bron_id,
            "geometry": connection_point,
        }
        record.update(_puntattributen(puntobject))
        records.append(record)

    def add_node_connections(
        positions: Iterable[int],
        connection_point: Point,
        puntobject: pd.Series | None,
    ) -> None:
        node_endpoints = [
            _Endpoint(
                segment_id=str(endpoints.iloc[position]["segment_id"]),
                bron_id=str(endpoints.iloc[position]["bron_id"]),
                direction=str(endpoints.iloc[position]["direction"]),
                geometry=endpoints.geometry.iloc[position],
            )
            for position in positions
        ]
        for first_endpoint, second_endpoint in _directed_connection_pairs(
            node_endpoints
        ):
            add_connection(
                first_endpoint,
                second_endpoint,
                connection_point,
                puntobject,
            )

    point_nodes: list[tuple[list[int], pd.Series]] = []
    point_node_positions: set[int] = set()
    if point_index is not None:
        for _, puntobject in punten.iterrows():
            point = puntobject.geometry
            query_geometry = point if tolerance == 0 else point.buffer(tolerance)
            candidate_positions = endpoint_index.query(
                query_geometry,
                predicate="intersects",
            )
            matching_positions = [
                position
                for position in candidate_positions
                if point.distance(endpoints.geometry.iloc[position]) <= tolerance
            ]
            source_ids = {
                str(endpoints.iloc[position]["bron_id"])
                for position in matching_positions
            }
            if len(source_ids) < 2:
                continue
            endpoint_locations = {
                endpoints.geometry.iloc[position].wkb for position in matching_positions
            }
            if len(endpoint_locations) == 1:
                continue
            point_nodes.append((matching_positions, puntobject))
            point_node_positions.update(matching_positions)

    for positions in endpoint_groups.values():
        if point_node_positions.intersection(positions):
            continue
        segment_ids = {
            str(endpoints.iloc[position]["segment_id"]) for position in positions
        }
        if len(segment_ids) < 2:
            continue
        connection_point = endpoints.geometry.iloc[positions[0]]
        puntobject = (
            _nearest_puntobject(
                connection_point,
                punten,
                point_index,
                tolerance=tolerance,
            )
            if point_index is not None
            else None
        )
        add_node_connections(positions, connection_point, puntobject)

    for positions, puntobject in point_nodes:
        add_node_connections(positions, puntobject.geometry, puntobject)

    if not records:
        return _empty_verbindingen()
    verbindingen = gpd.GeoDataFrame(records, geometry="geometry", crs=settings.crs)
    logger.info(
        "Created %s unique connections between %s hydroobject segments",
        len(verbindingen),
        len(segmenten),
    )
    return verbindingen


def split_hydroobjecten_by_length(
    hydroobjecten: gpd.GeoDataFrame,
    *,
    max_length: float,
) -> gpd.GeoDataFrame:
    """Split lines into equal-length segments no longer than ``max_length``.

    The number of segments is the smallest integer that keeps each segment at
    or below ``max_length``. The source line length is then divided equally
    over those segments. Source fields and ``bron_id`` are retained.
    ``segment_id`` is based on the source identifier and a deterministic,
    one-based sequence number.
    """
    if max_length <= 0:
        raise ValueError("max_length must be greater than zero")
    lines = _prepare_hydroobjecten(hydroobjecten)
    if lines.empty:
        lines["segment_id"] = pd.Series(dtype="object")
        return lines

    records: list[dict[str, object]] = []
    segment_numbers: defaultdict[str, int] = defaultdict(int)
    for index, row in lines.iterrows():
        line = row.geometry
        source_id = _source_identifier(row, index)
        segment_count = math.ceil(line.length / max_length)
        segment_length = line.length / segment_count
        for segment_index in range(segment_count):
            start = segment_index * segment_length
            end = min(start + segment_length, line.length)
            segment = substring(line, start, end)
            if (
                not isinstance(segment, LineString)
                or segment.is_empty
                or segment.length == 0
            ):
                continue
            segment_numbers[source_id] += 1
            record = row.drop(labels="geometry").to_dict()
            record["segment_id"] = f"{source_id}:{segment_numbers[source_id]:04d}"
            record["geometry"] = segment
            records.append(record)

    if not records:
        result = lines.iloc[0:0].copy()
        result["segment_id"] = pd.Series(dtype="object")
        return result
    result = gpd.GeoDataFrame(records, geometry="geometry", crs=settings.crs)
    if (result.geometry.length > max_length + POSITION_TOLERANCE).any():
        raise ValueError("Hydroobject segment exceeds max_length")
    logger.info(
        "Split %s hydroobjecten by max_length %s into %s segments",
        len(lines),
        max_length,
        len(result),
    )
    return result
