"""Standaard GeoParquet-uitvoer voor Hilbert-gesorteerde featurelagen."""

import json
import math
import os
import tempfile
from pathlib import Path

import geopandas as gpd
import pyarrow.parquet as pq

from waterlagen.logger import get_logger

logger = get_logger(__name__)

GEOPARQUET_ROW_GROUP_SIZE = 100_000


def _validate_geoparquet(path: Path, *, expected_feature_count: int) -> None:
    """Validate standard GeoParquet metadata without loading all features."""
    metadata = pq.read_metadata(path)
    if metadata.num_rows != expected_feature_count:
        raise ValueError(
            f"GeoParquet has {metadata.num_rows} features; expected {expected_feature_count}"
        )
    if b"geo" not in (metadata.metadata or {}):
        raise ValueError("Parquet output has no GeoParquet metadata")
    geo_metadata = json.loads(metadata.metadata[b"geo"].decode("utf-8"))
    primary_column = geo_metadata.get("primary_column")
    columns = geo_metadata.get("columns")
    if not isinstance(primary_column, str) or not isinstance(columns, dict):
        raise ValueError("Parquet output has invalid GeoParquet metadata")
    covering = columns.get(primary_column, {}).get("covering", {})
    bbox_paths = covering.get("bbox")
    if not isinstance(bbox_paths, dict):
        raise ValueError("Parquet output has no standard GeoParquet bbox covering")
    if expected_feature_count:
        expected_statistics_paths = {
            ".".join(path)
            for path in bbox_paths.values()
            if isinstance(path, list) and all(isinstance(part, str) for part in path)
        }
        statistics_paths = {
            metadata.row_group(row_group_index).column(column_index).path_in_schema
            for row_group_index in range(metadata.num_row_groups)
            for column_index in range(metadata.row_group(row_group_index).num_columns)
            if metadata.row_group(row_group_index).column(column_index).statistics
            is not None
        }
        if not expected_statistics_paths <= statistics_paths:
            raise ValueError("Parquet output has no statistics for its bbox covering")
    expected_row_groups = max(
        1,
        math.ceil(expected_feature_count / GEOPARQUET_ROW_GROUP_SIZE),
    )
    if metadata.num_row_groups != expected_row_groups:
        raise ValueError(
            f"GeoParquet has {metadata.num_row_groups} row groups; "
            f"expected {expected_row_groups}"
        )


def write_geoparquet_atomically(
    features: gpd.GeoDataFrame,
    target_path: Path,
    *,
    overwrite: bool = True,
) -> Path:
    """Write standard, bbox-covered GeoParquet and atomically replace a target.

    The caller is responsible for applying any physical ordering before this
    function is called. GeoParquet row groups retain that row order, while the
    standard covering ``bbox`` column and its Parquet statistics support spatial
    row-group pruning by compatible readers.
    """
    if features.crs is None:
        raise ValueError("GeoParquet output features have no CRS")

    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists() and not overwrite:
        logger.info("Reusing GeoParquet output from %s", target_path)
        return target_path

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=".parquet",
        dir=target_path.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink(missing_ok=True)
    try:
        features.to_parquet(
            temporary_path,
            index=False,
            compression="zstd",
            geometry_encoding="WKB",
            schema_version="1.1.0",
            write_covering_bbox=True,
            row_group_size=GEOPARQUET_ROW_GROUP_SIZE,
            write_statistics=True,
        )
        _validate_geoparquet(temporary_path, expected_feature_count=len(features))
        temporary_path.replace(target_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return target_path
