from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from waterlagen.ahn import productie


def test_ahn_priority_and_version_map(tmp_path: Path) -> None:
    sources = {
        4: [[400, 401, 402, -32768, 404]],
        5: [[500, 501, -32768, -32768, 504]],
        6: [[600, -32768, -32768, -32768, -32768]],
    }
    paths = {}
    for version, values in sources.items():
        path = tmp_path / f"ahn{version}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=5,
            height=1,
            count=1,
            dtype="int16",
            transform=from_origin(100000, 510000, 0.5, 0.5),
            crs=7415 if version == 6 else 28992,
            nodata=-32768,
        ) as ds:
            ds.scales = (0.01,)
            ds.write(np.array(values, dtype="int16"), 1)
        paths[path] = version

    target = tmp_path / "ahn.vrt"
    productie._mosaic(target, paths)
    with rasterio.open(target) as dem:
        assert dem.crs.to_epsg() == 28992
        assert dem.scales == (0.01,)
        np.testing.assert_array_equal(dem.read(1), [[600, 501, 402, -32768, 504]])
    with rasterio.open(tmp_path / "ahn_versie.vrt") as source:
        assert source.nodata == 0
        np.testing.assert_array_equal(source.read(1), [[6, 5, 4, 0, 5]])

    result = productie.export_ahn_versions(
        tmp_path / "ahn_versie.vrt", [target], tmp_path / "export"
    )
    with rasterio.open(result) as source:
        np.testing.assert_array_equal(source.read(1), [[6, 5, 4, 0, 5]])
