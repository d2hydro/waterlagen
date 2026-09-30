"""Land-use location relative to the LIWO outside-area polygons."""

import geopandas as gpd
import pandas as pd
from shapely.geometry.base import BaseGeometry


def _buitendijks_mask(
    objects: gpd.GeoDataFrame, buitendijks_area: BaseGeometry
) -> pd.Series:
    """Use representative points; polygon boundaries count as buitendijks."""
    return objects.geometry.representative_point().covered_by(buitendijks_area)
