"""Teken een bronlaag in het raster; latere lagen overschrijven eerdere lagen."""

import geopandas as gpd
import numpy as np
from affine import Affine
from rasterio import enums, features
from shapely.geometry.base import BaseGeometry


def rasterize_features(
    raster: np.ndarray,
    data: gpd.GeoDataFrame,
    transform: Affine,
    *,
    value_column: str = "code",
    all_touched: bool = True,
) -> np.ndarray:
    """Rasterize features in place, including explicit NoData codes.

    Parameters
    ----------
    raster : numpy.ndarray
        Existing raster; intersecting cells are overwritten in source row order.
    data : geopandas.GeoDataFrame
        Geometry and class codes. Missing codes and empty geometries are skipped.
        An explicit code 0 is written, clearing previous land use in those cells.
    transform : affine.Affine
        Transform of the supplied raster.
    value_column : str, optional
        Name of the column containing numeric class codes.
    all_touched : bool, optional
        Include every cell touched by a geometry, by default True.

    Returns
    -------
    numpy.ndarray
        The supplied array, modified in place.
    """
    if data.empty:
        return raster

    valid = data.dropna(subset=[value_column, "geometry"])
    if valid.empty:
        return raster

    shapes: list[tuple[BaseGeometry, int]] = [
        (geometry, int(code))
        for geometry, code in zip(valid.geometry, valid[value_column], strict=True)
        if not geometry.is_empty
    ]
    if not shapes:
        return raster

    features.rasterize(
        shapes,
        out=raster,
        transform=transform,
        all_touched=all_touched,
        merge_alg=enums.MergeAlg.replace,
    )
    return raster
