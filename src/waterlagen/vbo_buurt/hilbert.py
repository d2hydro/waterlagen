"""Ruimtelijke ordening van woon-VBO's met een Hilbert-index."""

from time import perf_counter

import geopandas as gpd
import pandas as pd

from waterlagen._crs import same_crs
from waterlagen.logger import get_logger

logger = get_logger(__name__)

HILBERT_COLUMN = "_hilbert"
# Geldigheidsgebied van RD New voor Nederland, in meters (EPSG:28992).
# Deze vaste extent maakt de index onafhankelijk van de datasetversie of subset.
NEDERLAND_RD_BOUNDS = (-7_000.0, 289_000.0, 300_000.0, 629_000.0)
# GeoPandas ondersteunt levels 1 tot en met 16. Level 16 geeft een 65.536 x
# 65.536-grid en een Hilbert-waarde in het bereik [0, 2^32 - 1].
HILBERT_LEVEL = 16


def sorteer_op_hilbert(features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add a vectorized Hilbert index and sort point features by that index.

    ``features`` is updated in place with :data:`HILBERT_COLUMN` before the
    unavoidable sorted GeoDataFrame is created. The fixed national RD extent
    makes the resulting order stable across full datasets and subsets.
    """
    if features.crs is None:
        raise ValueError("VBO features have no CRS for Hilbert ordering")
    if not same_crs(features.crs, "EPSG:28992"):
        raise ValueError("Hilbert ordering requires VBO features in EPSG:28992")
    if features.geometry.isna().any() or features.geometry.is_empty.any():
        raise ValueError("Hilbert ordering requires non-empty VBO geometries")
    if not features.geometry.geom_type.eq("Point").all():
        raise ValueError("Hilbert ordering requires VBO point geometries")

    minx, miny, maxx, maxy = features.geometry.total_bounds
    extent_minx, extent_miny, extent_maxx, extent_maxy = NEDERLAND_RD_BOUNDS
    if (
        minx < extent_minx
        or miny < extent_miny
        or maxx > extent_maxx
        or maxy > extent_maxy
    ):
        raise ValueError("VBO geometries fall outside the fixed Nederlandse RD extent")

    started = perf_counter()
    features[HILBERT_COLUMN] = features.geometry.hilbert_distance(
        total_bounds=NEDERLAND_RD_BOUNDS,
        level=HILBERT_LEVEL,
    ).astype("uint64")
    logger.info("Calculated VBO Hilbert indices in %.1f s", perf_counter() - started)

    started = perf_counter()
    sorted_features = features.sort_values(
        HILBERT_COLUMN,
        kind="stable",
        ignore_index=True,
    )
    logger.info("Sorted VBO's by Hilbert index in %.1f s", perf_counter() - started)
    valideer_hilbert_volgorde(sorted_features)
    return sorted_features


def valideer_hilbert_volgorde(features: pd.DataFrame) -> None:
    """Validate the technical Hilbert ordering invariant of VBO point data."""
    if HILBERT_COLUMN not in features.columns:
        raise ValueError("VBO features have no Hilbert index")
    hilbert = features[HILBERT_COLUMN]
    if not pd.api.types.is_integer_dtype(hilbert):
        raise ValueError("VBO Hilbert index must have an integer datatype")
    if hilbert.isna().any():
        raise ValueError("VBO Hilbert index contains missing values")
    if not hilbert.is_monotonic_increasing:
        raise ValueError("VBO Hilbert indices are not monotonically increasing")
