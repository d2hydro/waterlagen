import geopandas as gpd
import numpy as np
import pytest
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box

from waterlagen.functioneel_landgebruik.rasteriseren import rasterize_features


@pytest.mark.parametrize("column", ["code", "landgebruik-code", "code met spaties"])
def test_rasterize_preserves_priority_and_nodata_with_custom_column(column):
    raster = np.full((4, 4), 78, dtype="uint8")
    data = gpd.GeoDataFrame(
        {column: [30, 0, None, 100, 100]},
        geometry=[
            box(0, 0, 4, 4),
            box(1, 1, 3, 3),
            box(0, 0, 4, 4),
            None,
            Polygon(),
        ],
        crs="EPSG:28992",
    )

    result = rasterize_features(
        raster, data, from_origin(0, 4, 1, 1), value_column=column, all_touched=False
    )

    assert result is raster
    expected = np.full((4, 4), 30, dtype="uint8")
    expected[1:3, 1:3] = 0  # Open BAG-keuze wist eerder ingetekend landgebruik.
    np.testing.assert_array_equal(result, expected)
