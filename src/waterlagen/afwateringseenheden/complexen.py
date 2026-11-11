"""Exclude short parallel routes from targets without changing burn eligibility."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
import json
import math

import geopandas as gpd
from shapely.geometry import Point

from waterlagen.logger import get_logger

from .lines import (
    _prepare_hydroobjecten,
    _prepare_puntobjecten,
    create_hydroobject_verbindingen,
    split_hydroobjecten_at_points,
)

COMPLEX_POLICY = "parallel_routes_length_v1"
logger = get_logger(__name__)


def validate_complex_length(value: float) -> None:
    """Require a finite, non-negative maximum route length."""
    if not math.isfinite(value) or value < 0:
        raise ValueError("max_complex_routelengte must be finite and non-negative")


@dataclass(frozen=True)
class _Edge:
    first: int
    last: int
    source: str
    length: float
    works: frozenset[str]


def _blocks(adjacency: dict[int, list[int]], edges: list[_Edge]):
    """Yield vertex-biconnected edge blocks, preserving multiedges, iteratively."""
    discovery = {}
    low = {}
    stack = []
    clock = 0
    for root in adjacency:
        if root in discovery:
            continue
        clock += 1
        discovery[root] = low[root] = clock
        frames = [(root, None, iter(adjacency[root]))]
        while frames:
            node, parent_edge, neighbors = frames[-1]
            edge_id = next(neighbors, None)
            if edge_id is None:
                frames.pop()
                if parent_edge is not None:
                    parent = frames[-1][0]
                    low[parent] = min(low[parent], low[node])
                    if low[node] >= discovery[parent]:
                        block = set()
                        while stack:
                            popped = stack.pop()
                            block.add(popped)
                            if popped == parent_edge:
                                break
                        yield block
                continue
            if edge_id == parent_edge:
                continue
            edge = edges[edge_id]
            other = edge.last if edge.first == node else edge.first
            if other not in discovery:
                stack.append(edge_id)
                clock += 1
                discovery[other] = low[other] = clock
                frames.append((other, edge_id, iter(adjacency[other])))
            elif discovery[other] < discovery[node]:
                stack.append(edge_id)
                low[node] = min(low[node], discovery[other])


def _routes(local, edges, first, last):
    """Walk every branch of a simple ring or theta block."""
    routes = []
    for initial in local[first]:
        node = first
        edge_id = initial
        route = []
        internal = []
        seen = {first}
        while True:
            route.append(edge_id)
            edge = edges[edge_id]
            node = edge.last if edge.first == node else edge.first
            if node == last:
                break
            if node in seen or len(local[node]) != 2:
                return []
            seen.add(node)
            internal.append(node)
            edge_id = next(
                candidate for candidate in local[node] if candidate != edge_id
            )
        routes.append((route, internal))
    return routes


def excluded_complex_sources(
    primary: gpd.GeoDataFrame,
    points: gpd.GeoDataFrame,
    culvert_pieces: gpd.GeoDataFrame | None,
    *,
    tolerance: float,
    maximum: float,
) -> set[str]:
    """Return full source IDs in short parallel groups with a work on each route.

    Only the returned target selection changes. Source geometry and burn flags
    are never modified. Complete source geometry is used before length splitting.
    Point works require ``objecttype`` stuw or gemaal; matched culvert pieces
    represent the duiker-, sifon- and hevelroutes.
    """
    validate_complex_length(maximum)
    if maximum == 0 or primary.empty:
        return set()
    primary = _prepare_hydroobjecten(primary)
    points = _prepare_puntobjecten(points)
    pieces = split_hydroobjecten_at_points(
        primary, points, tolerance=tolerance
    ).hydroobject_segmenten.reset_index(drop=True)
    pieces["segment_key"] = [str(i) for i in range(len(pieces))]
    connections = create_hydroobject_verbindingen(pieces, points, tolerance=tolerance)
    parents = list(range(2 * len(pieces)))

    def root(node):
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node

    def join(first, last):
        parents[root(first)] = root(last)

    coordinates = {}
    endpoints = []
    keys = {}
    for index, row in pieces.iterrows():
        keys[row.segment_key] = index
        for side, coordinate in enumerate(
            (row.geometry.coords[0], row.geometry.coords[-1])
        ):
            endpoint = 2 * index + side
            endpoints.append(Point(coordinate))
            if coordinate in coordinates:
                join(endpoint, coordinates[coordinate])
            coordinates[coordinate] = endpoint
    # The minimal connection tree determines node equivalence only. All physical
    # edges, including parallel edges, remain in the research graph.
    for row in connections.itertuples():
        ends = []
        for key in (row.van_segment_key, row.naar_segment_key):
            index = keys[key]
            ends.append(
                min(
                    (2 * index, 2 * index + 1),
                    key=lambda n: endpoints[n].distance(row.geometry),
                )
            )
        join(*ends)
    node_works = defaultdict(set)
    # read_puntobjecten records the source layer in objecttype. Other point
    # objects can still split/connect lines, but do not supply a route work.
    structure_points = points.loc[points.objecttype.isin(("stuw", "gemaal"))]
    if not structure_points.empty:
        point_index = structure_points.sindex
        for index, endpoint in enumerate(endpoints):
            query = endpoint if tolerance == 0 else endpoint.buffer(tolerance)
            for position in point_index.query(query, predicate="intersects"):
                if (
                    endpoint.distance(structure_points.geometry.iloc[position])
                    <= tolerance
                ):
                    node_works[root(index)].add(
                        "point:" + str(structure_points.iloc[position].bron_id)
                    )
    culverts_by_source = defaultdict(list)
    if culvert_pieces is not None:
        for row in culvert_pieces.itertuples():
            ids = json.loads(row.duiker_ids)
            if ids:
                culverts_by_source[str(row.bron_id)].append((row.geometry, ids))
    edges = []
    adjacency = defaultdict(list)
    source_edges = defaultdict(set)
    for index, row in pieces.iterrows():
        works = set()
        for geometry, ids in culverts_by_source[str(row.bron_id)]:
            if row.geometry.intersection(geometry).length > 0:
                works.update("culvert:" + str(identifier) for identifier in ids)
        edge = _Edge(
            root(2 * index),
            root(2 * index + 1),
            str(row.bron_id),
            row.geometry.length,
            frozenset(works),
        )
        edges.append(edge)
        adjacency[edge.first].append(index)
        adjacency[edge.last].append(index)
        source_edges[edge.source].add(index)
    excluded = set()
    groups = 0
    for block in _blocks(adjacency, edges):
        if len(block) < 2:
            continue
        local = defaultdict(list)
        for index in block:
            local[edges[index].first].append(index)
            local[edges[index].last].append(index)
        if any(edges[index].first == edges[index].last for index in block):
            continue
        branches = [node for node in local if len(local[node]) > 2]
        if len(branches) == 2:
            pairs = [branches]
        elif not branches:
            contacts = [
                node for node in local if len(adjacency[node]) > len(local[node])
            ]
            pairs = combinations(contacts, 2)
        else:
            continue
        sources = {edges[index].source for index in block}
        if any(not source_edges[source].issubset(block) for source in sources):
            continue
        for first, last in pairs:
            routes = _routes(local, edges, first, last)
            if len(routes) < 2:
                continue
            eligible = True
            route_works = []
            for route, internal in routes:
                length = math.fsum(edges[index].length for index in route)
                works = set().union(*(edges[index].works for index in route))
                works.update(work for node in internal for work in node_works[node])
                route_works.append(works)
                if not 0 < length <= maximum or not works:
                    eligible = False
                    break
            if eligible:
                # One duplicated registration cannot serve as the own work of
                # several parallel routes. Keep point and line namespaces apart.
                eligible = all(
                    works
                    - set().union(
                        *(other for j, other in enumerate(route_works) if i != j)
                    )
                    for i, works in enumerate(route_works)
                )
            if eligible:
                excluded.update(sources)
                groups += 1
                break
    logger.info(
        "Excluded %s parallel groups (%s source objects), maximum route length %s m",
        groups,
        len(excluded),
        maximum,
    )
    return excluded
