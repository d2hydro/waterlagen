"""Shared production areas on the existing national tile grid."""

from enum import StrEnum

import geopandas as gpd


class Area(StrEnum):
    """Supported production areas."""

    nederland = "nederland"
    alkmaar = "alkmaar"


def resolve_workers(workers: int | None, default: int) -> int:
    """Resolve an optional CLI override; reject non-positive worker counts."""
    value = default if workers is None else workers
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("workers must be a positive integer")
    return value


def select_area_tiles(tiles: gpd.GeoDataFrame, area: Area) -> gpd.GeoDataFrame:
    """Select complete tile cores for an area without changing their grid."""
    area = Area(area)
    if tiles.empty or tiles.tile_id.duplicated().any():
        raise ValueError("Tile index must be nonempty with unique tile IDs")
    if area == Area.nederland:
        return tiles.sort_values(["ymin", "xmin"]).reset_index(drop=True)
    sizes = (tiles.xmax - tiles.xmin).unique()
    if (
        len(sizes) != 1
        or sizes[0] <= 0
        or not (tiles.ymax - tiles.ymin).eq(sizes[0]).all()
    ):
        raise ValueError("Landgebruik vereist een regelmatig vierkant tegelrooster")
    size = int(sizes[0])
    origin_x, origin_y = int(tiles.xmin.min()), int(tiles.ymin.min())
    corner_x = origin_x + round((111000 - origin_x) / size) * size
    corner_y = origin_y + round((516000 - origin_y) / size) * size
    selected = tiles[
        tiles.xmin.isin([corner_x - size, corner_x])
        & tiles.ymin.isin([corner_y - size, corner_y])
    ]
    if len(selected) != 4:
        raise ValueError("Rooster bevat geen volledig 2x2-blok rond Alkmaar")
    return selected.sort_values(["ymin", "xmin"]).reset_index(drop=True)
