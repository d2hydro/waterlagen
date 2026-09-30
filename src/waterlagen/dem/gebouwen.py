"""One original-AHN elevation for each complete prepared building footprint."""

from math import ceil, floor

import geopandas as gpd
import numpy as np
import rasterio
from affine import Affine
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds
from rasterio.windows import bounds as window_bounds
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from waterlagen.logger import get_logger

from .config import DemConfig

logger = get_logger(__name__)


def aligned_window(
    bounds: tuple[float, float, float, float], transform: Affine
) -> Window:
    """Enclose bounds using integer offsets on an existing pixel grid."""
    window = from_bounds(*bounds, transform=transform)
    col, row = floor(window.col_off), floor(window.row_off)
    return Window(
        col,
        row,
        ceil(window.col_off + window.width) - col,
        ceil(window.row_off + window.height) - row,
    )


def _sample_building(
    geometry: BaseGeometry,
    ahn: rasterio.io.DatasetReader,
    buildings: gpd.GeoDataFrame,
    config: DemConfig,
) -> tuple[float, float, int]:
    """Search original AHN only; return NaN and diagnostics if unresolved."""
    radius = config.building_initial_buffer_m
    while True:
        exterior = geometry.buffer(radius).difference(geometry)
        window = aligned_window(exterior.bounds, ahn.transform)
        raw = ahn.read(1, window=window, boundless=True, masked=True)
        transform = ahn.window_transform(window)
        valid = ~np.ma.getmaskarray(raw) & np.isfinite(raw.data)
        inside = geometry_mask([exterior], raw.shape, transform, invert=True)
        # Include geometries touching candidate pixels even when the geometry
        # itself lies just outside the circular search ring (all_touched rule).
        sample_extent = box(*window_bounds(window, ahn.transform))
        neighbours = buildings.iloc[
            buildings.sindex.query(sample_extent, predicate="intersects")
        ]
        if not neighbours.empty:
            # These are the complete prepared land-use geometries, never a new
            # BAG selection. The burn mask itself always comes from source 10.
            excluded = geometry_mask(
                neighbours.geometry, raw.shape, transform, invert=True, all_touched=True
            )
            valid &= ~excluded
        donors = raw.data[valid & inside].astype("float64")
        if donors.size:
            elevations = donors * ahn.scales[0] + ahn.offsets[0]
            return (
                float(
                    np.percentile(
                        elevations, config.building_percentile, method="linear"
                    )
                ),
                radius,
                int(donors.size),
            )
        if radius >= config.building_max_search_distance_m:
            return float("nan"), radius, 0
        radius = min(
            radius + config.building_buffer_step_m,
            config.building_max_search_distance_m,
        )


def calculate_building_elevations(
    buildings: gpd.GeoDataFrame,
    selected_ids: set[int],
    ahn: rasterio.io.DatasetReader,
    config: DemConfig,
) -> gpd.GeoDataFrame:
    """Sample complete footprints once, retaining unresolved buildings.

    Parameters
    ----------
    buildings : geopandas.GeoDataFrame
        Complete prepared land-use geometries with gebouw_id and identificatie.
        Includes neighbours for donor exclusion.
    selected_ids : set of int
        IDs actually present in source-code-10 output cells.
    ahn : rasterio.io.DatasetReader
        Original DTM, including surrounding donor coverage.
    config : DemConfig
        Search distances and percentile.

    Returns
    -------
    geopandas.GeoDataFrame
        One row per selected ID with hoogte_m, zoekafstand_m and donor_aantal.
        Unresolved heights are NaN and are not a production failure.
    """
    result = buildings[buildings.gebouw_id.isin(selected_ids)].copy()
    if set(result.gebouw_id) != selected_ids:
        raise ValueError("Prepared footprints missing for selected building IDs")
    heights, radii, counts = [], [], []
    for number, geometry in enumerate(result.geometry, 1):
        elevation, radius, count = _sample_building(geometry, ahn, buildings, config)
        heights.append(elevation)
        radii.append(radius)
        counts.append(count)
        if number % 1000 == 0:
            logger.info("Building elevations: %s/%s", number, len(result))
    result["hoogte_m"] = np.asarray(heights, dtype="float64")
    result["zoekafstand_m"] = np.asarray(radii, dtype="float64")
    result["donor_aantal"] = np.asarray(counts, dtype="int64")
    logger.info(
        "Building elevations complete: %s buildings, %s unresolved",
        len(result),
        int(result.hoogte_m.isna().sum()),
    )
    return result
