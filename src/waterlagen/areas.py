"""Shared input selections; areas never clip production outputs."""

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon
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
    )
}
NAMED_AREAS_CRS = "EPSG:28992"


class Area(StrEnum):
    """Built-in names retained for Python callers."""

    nederland = "nederland"
    alkmaar = "alkmaar"


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


def area_name(value: str | Area | ProductionArea) -> str:
    """Validate a named area or water authority code without performing I/O."""
    name = value.value if isinstance(value, ProductionArea) else str(value)
    if name in {"nederland", *NAMED_AREAS}:
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
        Named polygon, Nederland, or a water authority code.
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
