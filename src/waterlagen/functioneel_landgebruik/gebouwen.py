"""Persist building identity alongside the exact land-use building cells."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen.logger import get_logger
from waterlagen.raster.overviews import build_raster_overviews

logger = get_logger(__name__)


def building_paths(target: Path) -> tuple[Path, Path]:
    """Return companion ID raster and complete prepared footprint paths."""
    return (
        target.parent / "gebouw_ids" / target.name,
        target.parent / "gebouwen" / target.with_suffix(".gpkg").name,
    )


def ensure_building_index(source: Path, target: Path, layer: str = "pand") -> Path:
    """Create a stable UInt32 lookup, retaining the original BAG string IDs.

    Parameters
    ----------
    source, target : pathlib.Path
        BAG GeoPackage and output SQLite lookup. A matching index is reused;
        a changed source is rejected instead of reassigning existing IDs.
    layer : str
        Source building layer, default ``pand``.

    Returns
    -------
    pathlib.Path
        Read-only lookup used by every land-use worker in this production.
    """
    stat = source.stat()
    identity = json.dumps(
        [str(source.resolve()), stat.st_size, stat.st_mtime_ns, layer]
    )
    if target.exists():
        with closing(sqlite3.connect(target)) as conn:
            if conn.execute("SELECT identity FROM metadata").fetchone()[0] != identity:
                raise ValueError(
                    "Building index source changed; use a new production folder"
                )
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp.sqlite")
    temporary.unlink(missing_ok=True)
    try:
        with closing(
            sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
        ) as src:
            quoted = '"' + layer.replace('"', '""') + '"'
            rows = src.execute(
                f"SELECT DISTINCT identificatie FROM {quoted} ORDER BY identificatie"
            )
            with closing(sqlite3.connect(temporary)) as dst:
                dst.execute(
                    "CREATE TABLE gebouwen (gebouw_id INTEGER PRIMARY KEY, identificatie TEXT UNIQUE NOT NULL)"
                )
                for number, (identificatie,) in enumerate(rows, 1):
                    if identificatie is None or number > np.iinfo(np.uint32).max:
                        raise ValueError(
                            "Missing building identity or too many buildings for UInt32"
                        )
                    dst.execute(
                        "INSERT INTO gebouwen VALUES (?, ?)",
                        (number, str(identificatie)),
                    )
                dst.execute("CREATE TABLE metadata (identity TEXT NOT NULL)")
                dst.execute("INSERT INTO metadata VALUES (?)", (identity,))
                dst.commit()
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    logger.info("Building identity index ready: %s", target)
    return target


def identify_buildings(
    buildings: gpd.GeoDataFrame, index_path: Path
) -> gpd.GeoDataFrame:
    """Attach stable IDs to prepared rows without changing their order."""
    result = buildings[["identificatie", "geometry"]].copy()
    with closing(sqlite3.connect(index_path)) as conn:
        ids = []
        for identifier in result.identificatie:
            row = conn.execute(
                "SELECT gebouw_id FROM gebouwen WHERE identificatie=?",
                (str(identifier),),
            ).fetchone()
            if row is None:
                raise ValueError(f"Building missing from identity lookup: {identifier}")
            ids.append(row[0])
    result["gebouw_id"] = np.asarray(ids, dtype="uint32")
    return result


def write_buildings(
    target: Path,
    ids: np.ndarray,
    buildings: gpd.GeoDataFrame,
    profile: dict,
    metadata: dict,
    factors: tuple[int, ...],
) -> None:
    """Write a matched companion pair; land-use raster is committed last."""
    raster_path, geometry_path = building_paths(target)
    raster_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = raster_path.with_suffix(".tmp.tif")
    id_profile = dict(profile)
    id_profile.pop("photometric", None)
    id_profile.update(dtype="uint32", nodata=0)
    try:
        with rasterio.open(temporary, "w", **id_profile) as dst:
            dst.write(ids, 1)
            dst.update_tags(**metadata)
            build_raster_overviews(
                dst, factors=factors, resampling=rasterio.enums.Resampling.nearest
            )
        buildings = buildings.drop_duplicates("gebouw_id").copy()
        buildings["output_pair"] = metadata["output_pair"]
        write_geopackage_layer_atomically(
            buildings, geometry_path, layer_name="gebouwen"
        )
        temporary.replace(raster_path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_buildings(target: Path, min_context_m: float = 0.0) -> None:
    """Reject missing, stale or inconsistent companions on reuse."""
    import pyogrio

    ids_path, geometry_path = building_paths(target)
    if not ids_path.is_file() or not geometry_path.is_file():
        raise ValueError(
            "Building companions missing; rebuild land use with building_index_path"
        )
    with (
        rasterio.open(target) as landuse,
        rasterio.open(ids_path) as ids,
        rasterio.open(target.parent / "bronnen" / target.name) as sources,
    ):
        if float(ids.tags().get("building_context_m", 0)) < min_context_m:
            raise ValueError(
                "Building neighbour context is too small; rebuild land use with building_context_m"
            )
        if (ids.transform, ids.shape, ids.crs) != (
            landuse.transform,
            landuse.shape,
            landuse.crs,
        ) or ids.tags().get("output_pair") != landuse.tags().get("output_pair"):
            raise ValueError("Building companion grid or output_pair differs")
        if (sources.shape, sources.transform, sources.crs) != (
            landuse.shape,
            landuse.transform,
            landuse.crs,
        ) or sources.tags().get("output_pair") != landuse.tags().get("output_pair"):
            raise ValueError("Building source raster belongs to another output pair")
        for _, window in ids.block_windows(1):
            if not np.array_equal(
                ids.read(1, window=window) > 0, sources.read(1, window=window) == 10
            ):
                raise ValueError("Building IDs differ from source code 10")
        pairs = pyogrio.read_dataframe(
            geometry_path,
            layer="gebouwen",
            columns=["output_pair"],
            read_geometry=False,
        )
        if (
            not pairs.empty
            and not pairs.output_pair.eq(landuse.tags()["output_pair"]).all()
        ):
            raise ValueError("Building geometries belong to another output pair")
