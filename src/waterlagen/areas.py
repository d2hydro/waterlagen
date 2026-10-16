"""Shared input selections; areas never clip production outputs."""

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry

from waterlagen._crs import same_crs
from waterlagen._sources import SourcePreparation
from waterlagen.administratieve_gebieden import (
    DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
    bestuurlijke_gebieden_path,
    download_bestuurlijke_gebieden,
    download_waterschapsgrenzen,
    normaliseer_waterschapsgrenzen,
    read_landsgrens,
    read_waterschapsgrenzen_layer,
)
from waterlagen.administratieve_gebieden.download import WATERSCHAPSGRENZEN_FILENAME
from waterlagen.datastore import DataStore
from waterlagen.settings import settings

# Fixed RD polygons, independent of product, resolution and tile size.
NAMED_AREAS: dict[str, Polygon] = {
    "alkmaar": Polygon(
        [(105000, 510000), (115000, 510000), (115000, 520000), (105000, 520000)]
    ),
    # One square kilometre around the centre, inside a single 5 km and 10 km tile.
    "alkmaar_centrum": Polygon(
        [(111250, 515750), (112250, 515750), (112250, 516750), (111250, 516750)]
    ),
}
NAMED_AREAS_CRS = "EPSG:28992"


class Area(StrEnum):
    """Built-in names retained for Python callers."""

    nederland = "nederland"
    alkmaar = "alkmaar"
    alkmaar_centrum = "alkmaar_centrum"


@dataclass(frozen=True)
class ProductionArea:
    """Resolved input selection in the configured project CRS."""

    value: str
    geometry: BaseGeometry
    crs: str

    @property
    def identity(self) -> dict[str, str]:
        """Stable run identity, including the actual boundary and CRS."""
        return {
            "name": self.value,
            "crs": self.crs,
            "sha256": hashlib.sha256(self.geometry.normalize().wkb).hexdigest(),
        }


def area_from_bounds(bounds: Sequence[float]) -> ProductionArea:
    """Create a rectangular input selection without performing I/O.

    Parameters
    ----------
    bounds : sequence of float
        Four finite coordinates: xmin, ymin, xmax, ymax, in ``settings.crs``.
        Both maximum coordinates must exceed their minimum.

    Returns
    -------
    ProductionArea
        Bbox polygon with a canonical coordinate-based name. The selection
        does not clip production outputs or change their grids.

    Raises
    ------
    ValueError
        If the coordinates do not describe a finite, nonempty rectangle.
    """
    if len(bounds) != 4:
        raise ValueError("Bounds vereisen vier getallen: xmin ymin xmax ymax")
    try:
        coordinates = tuple(float(value) for value in bounds)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Bounds moeten eindige getallen zijn") from error
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("Bounds moeten eindige getallen zijn")
    coordinates = tuple(0.0 if value == 0 else value for value in coordinates)
    xmin, ymin, xmax, ymax = coordinates
    if xmin >= xmax or ymin >= ymax:
        raise ValueError("Bounds vereisen xmin < xmax en ymin < ymax")
    parts = []
    for value in coordinates:
        # Decimal preserves the shortest round-trippable float representation,
        # while fixed notation keeps names independent of exponent spelling.
        part = format(Decimal(str(value)), "f") if value != 0 else "0"
        if "." in part:
            part = part.rstrip("0").rstrip(".")
        parts.append(part)
    return ProductionArea("_".join(parts), box(*coordinates), settings.crs)


def area_name(value: str | Area | ProductionArea) -> str:
    """Validate a known name, water authority code or constructed bbox without I/O."""
    name = value.value if isinstance(value, ProductionArea) else str(value)
    if name in {"nederland", *NAMED_AREAS}:
        return name
    if isinstance(value, ProductionArea) and not value.geometry.is_empty:
        rectangle = area_from_bounds(value.geometry.bounds)
        if name == rectangle.value and value.geometry.equals(rectangle.geometry):
            return name
    code = name.removeprefix("waterschap_")
    if code.isascii() and code.isdigit():
        return f"waterschap_{code}"
    raise ValueError(
        f"Onbekend gebied: {name}; kies nederland, {', '.join(NAMED_AREAS)} of een waterschapscode"
    )


def resolve_area(
    area: str | Area | ProductionArea, store: DataStore, preparation: SourcePreparation
) -> ProductionArea:
    """Resolve a shared input selection, preparing its boundary when needed.

    Parameters
    ----------
    area : str or Area or ProductionArea
        Named polygon, Nederland, a water authority code, or a rectangle made
        with ``area_from_bounds``.
    store : DataStore
        Source cache locations.
    preparation : SourcePreparation
        Reuse, refresh and offline policy.

    Returns
    -------
    ProductionArea
        Nonempty polygon geometry in ``settings.crs``.
    """
    if isinstance(area, ProductionArea):
        area_name(area)
        if (
            area.geometry.is_empty
            or not area.geometry.is_valid
            or area.geometry.geom_type not in {"Polygon", "MultiPolygon"}
        ):
            raise ValueError("Gebied heeft geen geldige vlakgeometrie")
        if not same_crs(area.crs, settings.crs):
            raise ValueError("Gebieds-CRS verschilt van project-CRS")
        return ProductionArea(area_name(area), area.geometry, settings.crs)
    name = area_name(area)
    if name in NAMED_AREAS:
        frame = gpd.GeoDataFrame(geometry=[NAMED_AREAS[name]], crs=NAMED_AREAS_CRS)
    elif name == "nederland":
        frame = read_landsgrens(path=ensure_land_boundary(store, preparation))
    else:
        path = store.administratieve_gebieden_dir / WATERSCHAPSGRENZEN_FILENAME
        preparation.ensure(
            path,
            lambda: download_waterschapsgrenzen(
                download_dir=path.parent, overwrite=preparation.refresh, progress=False
            ),
        )
        frame = normaliseer_waterschapsgrenzen(read_waterschapsgrenzen_layer(path=path))
        frame = frame.loc[frame.waterbeheercode.eq(name.removeprefix("waterschap_"))]
    if frame.empty or frame.crs is None:
        raise ValueError(f"Geen gebied met geldig CRS gevonden: {name}")
    if not same_crs(frame.crs, settings.crs):
        frame = frame.to_crs(settings.crs)
    geometry = frame.geometry.make_valid().union_all()
    if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"Gebied heeft geen geldige vlakgeometrie: {name}")
    return ProductionArea(name, geometry, settings.crs)


def ensure_land_boundary(store: DataStore, preparation: SourcePreparation) -> Path:
    """Ensure the boundary needed by national raster grids and diagnostics."""
    year = DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR
    path = bestuurlijke_gebieden_path(
        year, download_dir=store.administratieve_gebieden_dir
    )
    return preparation.ensure(
        path,
        lambda: download_bestuurlijke_gebieden(
            year,
            download_dir=path.parent,
            overwrite=preparation.refresh,
            progress=False,
        ),
    )


def resolve_workers(workers: int | None, default: int) -> int:
    """Resolve an optional CLI override; reject non-positive worker counts."""
    value = default if workers is None else workers
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("workers must be a positive integer")
    return value


def select_area_tiles(
    tiles: gpd.GeoDataFrame, area: Area | ProductionArea
) -> gpd.GeoDataFrame:
    """Select complete intersecting cores; never clip or shift the raster grid."""
    if tiles.empty or tiles.tile_id.duplicated().any():
        raise ValueError("Tile index must be nonempty with unique tile IDs")
    if isinstance(area, ProductionArea):
        if not same_crs(tiles.crs, area.crs):
            raise ValueError("Tegel-CRS verschilt van gebieds-CRS")
        geometry = area.geometry
    elif Area(area) == Area.nederland:
        return tiles.sort_values(["ymin", "xmin"]).reset_index(drop=True)
    else:
        geometry = (
            gpd.GeoSeries([NAMED_AREAS[str(area)]], crs=NAMED_AREAS_CRS)
            .to_crs(tiles.crs)
            .iloc[0]
        )
    selected = tiles.loc[
        tiles.geometry.intersects(geometry) & ~tiles.geometry.touches(geometry)
    ]
    if selected.empty:
        raise ValueError("Rooster bevat geen tegels in het geselecteerde gebied")
    return selected.sort_values(["ymin", "xmin"]).reset_index(drop=True)
