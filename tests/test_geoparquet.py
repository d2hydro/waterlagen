import json

import geopandas as gpd
import pyarrow.parquet as pq
from shapely.geometry import Point

from waterlagen._geoparquet import (
    GEOPARQUET_ROW_GROUP_SIZE,
    write_geoparquet_atomically,
)


def test_write_geoparquet_writes_standard_bbox_covering_and_statistics(tmp_path):
    features = gpd.GeoDataFrame(
        {"_hilbert": [1, 2, 3], "waarde": [10, 20, 30]},
        geometry=[Point(1, 1), Point(2, 2), Point(3, 3)],
        crs="EPSG:28992",
    )
    target_path = tmp_path / "features.parquet"

    write_geoparquet_atomically(features, target_path)

    metadata = pq.read_metadata(target_path)
    geo_metadata = json.loads(metadata.metadata[b"geo"].decode("utf-8"))
    geometry_metadata = geo_metadata["columns"][geo_metadata["primary_column"]]
    assert metadata.num_row_groups == 1
    assert metadata.num_rows == len(features)
    assert "bbox" in geometry_metadata["covering"]
    bbox_paths = {
        ".".join(path) for path in geometry_metadata["covering"]["bbox"].values()
    }
    statistics_paths = {
        metadata.row_group(0).column(index).path_in_schema
        for index in range(metadata.row_group(0).num_columns)
        if metadata.row_group(0).column(index).statistics is not None
    }
    assert bbox_paths <= statistics_paths
    assert GEOPARQUET_ROW_GROUP_SIZE == 100_000

    output = gpd.read_parquet(target_path)
    assert output["_hilbert"].tolist() == [1, 2, 3]
    assert output.geometry.tolist() == features.geometry.tolist()

    filtered = gpd.read_parquet(target_path, bbox=(0, 0, 2.5, 2.5))
    assert filtered["_hilbert"].tolist() == [1, 2]


def test_write_geoparquet_supports_empty_feature_layers(tmp_path):
    features = gpd.GeoDataFrame(
        {"_hilbert": []},
        geometry=[],
        crs="EPSG:28992",
    )
    target_path = tmp_path / "empty.parquet"

    write_geoparquet_atomically(features, target_path)

    metadata = pq.read_metadata(target_path)
    assert metadata.num_rows == 0
    assert metadata.num_row_groups == 1
