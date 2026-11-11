"""Compare primary drainage targets using the recorded segment connections."""

from dataclasses import dataclass
from itertools import combinations
from math import isfinite
from pathlib import Path

import geopandas as gpd
from shapely import force_2d, line_merge
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

from waterlagen._crs import same_crs
from waterlagen._geopandas import read_file
from waterlagen.settings import settings


@dataclass(frozen=True)
class PrimaryRoutes:
    """Primary segment identifiers and their recorded continuations."""

    segment_ids: dict[str, int]
    neighbours: dict[int, set[int]]
    geometries: dict[int, LineString]

    def connects(self, first_key: str, second_key: str) -> bool:
        """Check both directions; unknown targets cannot confirm a connection."""
        if first_key not in self.segment_ids or second_key not in self.segment_ids:
            return False
        first = self.segment_ids[first_key]
        second = self.segment_ids[second_key]
        return self._reaches(first, second)

    def _reaches(self, start: int, destination: int) -> bool:
        """Follow recorded connections in either direction without revisiting cycles."""
        pending = [start]
        visited = set()
        while pending:
            current = pending.pop()
            if current == destination:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(self.neighbours[current] - visited)
        return False

    def connects_all(self, keys: set[str]) -> bool:
        """Every pair must belong to the same connected primary network."""
        if len(keys) < 2:
            return False
        return all(
            self.connects(first, second) for first, second in combinations(keys, 2)
        )


def read_primary_routes(run_dir: Path) -> PrimaryRoutes:
    """Read existing topology, retaining intermediate segments without own areas."""
    path = run_dir / "watersysteem.gpkg"
    if not path.is_file():
        raise FileNotFoundError(
            f"Primaire waterlopen voor signaalkaart ontbreken: {path}"
        )
    segments = read_file(path, layer="hydroobject_segment")
    connections = read_file(path, layer="hydroobject_verbinding")
    for features, columns in (
        (segments, ("segment_id", "segment_key")),
        (connections, ("van_segment", "naar_segment")),
    ):
        if features.crs is None or not same_crs(features.crs, settings.crs):
            raise ValueError("Signaalkaart: afwijkend CRS voor primaire verbindingen")
        if not set(columns).issubset(features.columns):
            raise ValueError(
                "Signaalkaart: ontbrekende velden voor primaire verbindingen"
            )
        if features[list(columns)].isna().any().any():
            raise ValueError(
                "Signaalkaart: lege identificatie in primaire verbindingen"
            )
    if (
        segments.segment_id.duplicated().any()
        or segments.segment_key.duplicated().any()
    ):
        raise ValueError("Signaalkaart: dubbele primaire segmentidentificatie")
    segment_ids = {
        str(row.segment_key): int(row.segment_id) for row in segments.itertuples()
    }
    geometries = {}
    for row in segments.itertuples():
        line = line_merge(force_2d(row.geometry))
        if (
            not isinstance(line, LineString)
            or not line.is_valid
            or not isfinite(line.length)
            or line.length <= 0
        ):
            raise ValueError("Signaalkaart: ongeldige geometrie van primair segment")
        geometries[int(row.segment_id)] = line
    neighbours: dict[int, set[int]] = {
        identifier: set() for identifier in segment_ids.values()
    }
    for row in connections.itertuples():
        source = int(row.van_segment)
        target = int(row.naar_segment)
        if source not in neighbours or target not in neighbours:
            raise ValueError("Signaalkaart: verbinding verwijst naar onbekend segment")
        neighbours[source].add(target)
        neighbours[target].add(source)
    return PrimaryRoutes(segment_ids, neighbours, geometries)


def culvert_target_points(
    geometry: BaseGeometry, areas: gpd.GeoDataFrame, routes: PrimaryRoutes
) -> dict[str, Point]:
    """Resolve both line ends, or one nearest-target point per positive polygon overlap."""
    nearby = areas.iloc[areas.sindex.query(geometry, predicate="intersects")]
    if geometry.geom_type in {"LineString", "MultiLineString"}:
        line = line_merge(geometry)
        if not isinstance(line, LineString):
            return {}
        targets = {}
        for point in (Point(line.coords[0]), Point(line.coords[-1])):
            containing = nearby.loc[nearby.contains(point), "segment_key"]
            if len(containing) != 1:
                return {}
            targets[str(containing.iloc[0])] = point
        return targets
    targets = {}
    for row in nearby.itertuples():
        overlap = row.geometry.intersection(geometry)
        if overlap.area <= 0:
            continue
        key = str(row.segment_key)
        if key not in routes.segment_ids:
            return {}
        target_line = routes.geometries[routes.segment_ids[key]]
        targets[key] = nearest_points(overlap, target_line)[0]
    return targets
