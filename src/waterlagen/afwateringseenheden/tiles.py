"""Tile orchestration for afwateringseenheden calculations."""

import os
import tempfile
from collections.abc import Collection, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from math import ceil, floor
import multiprocessing
from pathlib import Path
import traceback
from typing import Literal

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from waterlagen import datastore as default_datastore
from waterlagen._geopackage import write_geopackage_layer
from waterlagen.datastore import DataStore
from waterlagen.logger import get_logger
from waterlagen.raster.tiles import Tile, read_tiles, tile_from_row
from waterlagen.settings import settings

from .pcraster import (
    SUBCATCHMENTS_GPKG_FILENAME,
    SUBCATCHMENTS_LAYER,
    SubcatchmentResult,
    calculate_subcatchments,
)
from .raster import WatersysteemRasters, prepare_watersysteem_rasters

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AfwateringseenhedenTileResult:
    """Result for one afwateringseenheden tile calculation."""

    tile: Tile
    output_dir: Path
    rasters: WatersysteemRasters | None
    subcatchments: SubcatchmentResult | None
    usable_subcatchments: gpd.GeoDataFrame
    has_boundary_issue: bool = False
    skipped_reason: str | None = None


@dataclass(frozen=True, slots=True)
class AfwateringseenhedenTilesResult:
    """Results and merged output from a tiled afwateringseenheden workflow."""

    output_dir: Path
    tile_results: tuple[AfwateringseenhedenTileResult, ...]
    merged_path: Path | None
    merged_subcatchments: gpd.GeoDataFrame
    boundary_issue_tile_ids: tuple[str, ...]
    skipped_tile_ids: tuple[str, ...]


class AfwateringseenhedenTileError(RuntimeError):
    """Error raised by a worker while calculating one tile."""

    def __init__(self, tile_id: str, traceback_text: str) -> None:
        self.tile_id = tile_id
        self.traceback_text = traceback_text
        super().__init__(tile_id, traceback_text)

    def __str__(self) -> str:
        return (
            f"Failed afwateringseenheden tile {self.tile_id} in worker process:\n"
            f"{self.traceback_text}"
        )


class AfwateringseenhedenTilesError(RuntimeError):
    """Error raised when one or more tiled calculations failed."""

    def __init__(self, failures: dict[str, BaseException]) -> None:
        self.failures = failures
        details = "; ".join(
            f"{tile_id}: {type(error).__name__}: {error}"
            for tile_id, error in failures.items()
        )
        super().__init__(f"Failed afwateringseenheden tile(s): {details}")


@dataclass(frozen=True, slots=True)
class AfwateringseenhedenTileJob:
    """Serializable calculation settings for one afwateringseenheden tile."""

    tile: Tile
    output_dir: Path
    burn_depth_m: float
    ahn_vrt_path: Path | None
    watersysteem_path: Path
    data_store: DataStore
    tile_buffer_m: float
    resolution_m: float
    max_fill_depth_m: float
    overwrite: bool
    engine: Literal["pcraster"]


def _temporary_output_path(output_path: Path) -> Path:
    """Create an unused temporary GeoPackage path beside its target."""
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".gpkg",
        dir=output_path.parent,
    )
    os.close(fd)
    temporary_path = Path(temporary_name)
    temporary_path.unlink(missing_ok=True)
    return temporary_path


def _validate_tile_inputs(
    gebied: BaseGeometry,
    *,
    tile_size_m: int,
    tile_buffer_m: float,
    origin_x: int,
    origin_y: int,
) -> None:
    if gebied.is_empty:
        raise ValueError("gebied must not be empty")
    if not isinstance(tile_size_m, int) or isinstance(tile_size_m, bool):
        raise TypeError("tile_size_m must be an integer")
    if tile_size_m <= 0:
        raise ValueError("tile_size_m must be greater than zero")
    if tile_buffer_m < 0:
        raise ValueError("tile_buffer_m must not be negative")
    if not isinstance(origin_x, int) or isinstance(origin_x, bool):
        raise TypeError("origin_x must be an integer")
    if not isinstance(origin_y, int) or isinstance(origin_y, bool):
        raise TypeError("origin_y must be an integer")


def _resolve_worker_count(workers: int | None, *, tile_count: int) -> int:
    """Resolve, validate, and bound the requested or configured worker count."""
    if workers is None:
        workers = settings.afwateringseenheden_workers
    if not isinstance(workers, int) or isinstance(workers, bool):
        raise TypeError("workers must be an integer")
    if workers < 1:
        raise ValueError("workers must be at least 1")
    return min(workers, tile_count)


def _format_coordinate(value: int) -> str:
    if value < 0 or value > 999999:
        raise ValueError(
            f"Tile coordinate {value} cannot be represented as exactly six digits"
        )
    return f"{value:06d}"


def _tile_id(xmin: int, ymin: int, xmax: int, ymax: int) -> str:
    return (
        f"{_format_coordinate(xmin)}_"
        f"{_format_coordinate(ymin)}_"
        f"{_format_coordinate(xmax)}_"
        f"{_format_coordinate(ymax)}"
    )


def _snap_bounds(
    bounds: tuple[float, float, float, float],
    *,
    tile_size_m: int,
    origin_x: int,
    origin_y: int,
) -> tuple[int, int, int, int]:
    minx, miny, maxx, maxy = bounds
    xmin = origin_x + floor((minx - origin_x) / tile_size_m) * tile_size_m
    ymin = origin_y + floor((miny - origin_y) / tile_size_m) * tile_size_m
    xmax = origin_x + ceil((maxx - origin_x) / tile_size_m) * tile_size_m
    ymax = origin_y + ceil((maxy - origin_y) / tile_size_m) * tile_size_m
    return int(xmin), int(ymin), int(xmax), int(ymax)


def _tiles_for_gebied(
    gebied: BaseGeometry,
    *,
    tile_size_m: int,
    origin_x: int,
    origin_y: int,
) -> tuple[Tile, ...]:
    xmin, ymin, xmax, ymax = _snap_bounds(
        gebied.bounds,
        tile_size_m=tile_size_m,
        origin_x=origin_x,
        origin_y=origin_y,
    )
    tiles = []
    for y in range(ymin, ymax, tile_size_m):
        for x in range(xmin, xmax, tile_size_m):
            geometry = box(x, y, x + tile_size_m, y + tile_size_m)
            if not geometry.intersects(gebied):
                continue
            tiles.append(
                Tile(
                    tile_id=_tile_id(x, y, x + tile_size_m, y + tile_size_m),
                    column=(x - origin_x) // tile_size_m,
                    row=(y - origin_y) // tile_size_m,
                    xmin=x,
                    ymin=y,
                    xmax=x + tile_size_m,
                    ymax=y + tile_size_m,
                )
            )
    if not tiles:
        raise ValueError("No tiles intersect gebied")
    return tuple(tiles)


def _select_tiles(
    tiles: Iterable[Tile],
    tile_ids: Collection[str] | None,
) -> tuple[Tile, ...]:
    selected = tuple(tiles)
    if tile_ids is None:
        return selected
    if isinstance(tile_ids, (str, bytes)):
        raise TypeError("tile_ids must be a collection of strings, not a string")

    requested = {str(tile_id) for tile_id in tile_ids}
    available = {tile.tile_id for tile in selected}
    missing = sorted(requested - available)
    if missing:
        labels = ", ".join(missing)
        raise ValueError(f"Unknown tile ID(s): {labels}")
    return tuple(tile for tile in selected if tile.tile_id in requested)


def _read_intersecting_tiles(
    tiles_path: Path,
    gebied: BaseGeometry,
) -> tuple[Tile, ...]:
    tiles = read_tiles(tiles_path)
    if tiles.empty:
        raise ValueError("Tile index is empty")
    if "geometry" not in tiles.columns:
        raise ValueError("Tile index is missing required column: geometry")
    selected = tiles[tiles.geometry.intersects(gebied)].copy()
    if selected.empty:
        raise ValueError("No tiles from the tile index intersect gebied")
    return tuple(tile_from_row(row) for _, row in selected.iterrows())


def _tile_geometry(tile: Tile) -> BaseGeometry:
    return box(*tile.bounds)


def _calculation_geometry(tile: Tile, *, tile_buffer_m: float) -> BaseGeometry:
    geometry = _tile_geometry(tile)
    if tile_buffer_m == 0:
        return geometry
    return geometry.buffer(tile_buffer_m, join_style="mitre")


def _has_segment_cells(rasters: WatersysteemRasters) -> bool:
    with rasterio.open(rasters.hydroobject_segment_path) as segment:
        data = segment.read(1)
        nodata = segment.nodata if segment.nodata is not None else 0
    return bool(np.any(data != nodata))


def _empty_like_subcatchments(
    subcatchments: gpd.GeoDataFrame | None,
) -> gpd.GeoDataFrame:
    if subcatchments is not None:
        return subcatchments.iloc[0:0].copy()
    return gpd.GeoDataFrame(
        {
            "segment_fid": pd.Series(dtype="int64"),
            "segment_id": pd.Series(dtype="object"),
        },
        geometry=gpd.GeoSeries([], crs=None),
    )


def _read_existing_subcatchments(path: Path) -> gpd.GeoDataFrame | None:
    if not path.exists():
        return None
    try:
        return gpd.read_file(path, layer=SUBCATCHMENTS_LAYER)
    except Exception as exc:
        logger.warning(
            "Existing afwateringseenheden tile output %s is invalid and will be replaced: %s",
            path,
            exc,
        )
        return None


def _usable_subcatchments_for_tile(
    subcatchments: gpd.GeoDataFrame,
    *,
    tile: Tile,
    tile_buffer_m: float,
    resolution_m: float,
) -> tuple[gpd.GeoDataFrame, bool]:
    if subcatchments.empty:
        return subcatchments.copy(), False

    tile_geometry = _tile_geometry(tile)
    if tile_buffer_m > 0:
        boundary_distance = max(tile_buffer_m - resolution_m, 0)
        boundary_geometry = tile_geometry.buffer(
            boundary_distance,
            join_style="mitre",
        ).exterior
        boundary_hits = subcatchments.geometry.intersects(boundary_geometry)
    else:
        boundary_hits = pd.Series(False, index=subcatchments.index)

    boundary_issue = bool(
        subcatchments.loc[boundary_hits].geometry.intersects(tile_geometry).any()
    )
    usable = subcatchments.loc[~boundary_hits].copy()
    if usable.empty:
        return usable, boundary_issue

    clipped = gpd.clip(usable, tile_geometry)
    clipped = clipped[~clipped.geometry.is_empty].copy()
    return clipped.reset_index(drop=True), boundary_issue


def _calculate_tile(job: AfwateringseenhedenTileJob) -> AfwateringseenhedenTileResult:
    """Calculate or reuse one tile without sharing dataset handles with other jobs."""
    tile = job.tile
    tile_output_dir = job.output_dir
    tile_output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Calculating afwateringseenheden tile %s", tile.tile_id)

    existing_subcatchments_path = tile_output_dir / SUBCATCHMENTS_GPKG_FILENAME
    existing_subcatchments = None
    if not job.overwrite:
        existing_subcatchments = _read_existing_subcatchments(
            existing_subcatchments_path
        )

    if existing_subcatchments is None:
        rasters = prepare_watersysteem_rasters(
            _calculation_geometry(tile, tile_buffer_m=job.tile_buffer_m),
            burn_depth_m=job.burn_depth_m,
            ahn_vrt_path=job.ahn_vrt_path,
            watersysteem_path=job.watersysteem_path,
            output_dir=tile_output_dir,
            data_store=job.data_store,
            resolution_m=job.resolution_m,
            overwrite=job.overwrite,
        )
        if not _has_segment_cells(rasters):
            logger.info(
                "Skipping afwateringseenheden tile %s without hydroobject segments",
                tile.tile_id,
            )
            return AfwateringseenhedenTileResult(
                tile=tile,
                output_dir=tile_output_dir,
                rasters=rasters,
                subcatchments=None,
                usable_subcatchments=_empty_like_subcatchments(None),
                skipped_reason="no hydroobject_segment cells",
            )

        subcatchment_result = calculate_subcatchments(
            rasters,
            watersysteem_path=job.watersysteem_path,
            data_store=job.data_store,
            max_fill_depth_m=job.max_fill_depth_m,
            engine=job.engine,
        )
        subcatchments = subcatchment_result.subcatchments
    else:
        rasters = WatersysteemRasters(
            dem_path=tile_output_dir / "dem_2m.tif",
            hydroobject_segment_path=tile_output_dir / "hydroobject_segment.tif",
        )
        subcatchment_result = None
        subcatchments = existing_subcatchments
        logger.info("Reusing afwateringseenheden tile %s", tile.tile_id)

    usable_subcatchments, has_boundary_issue = _usable_subcatchments_for_tile(
        subcatchments,
        tile=tile,
        tile_buffer_m=job.tile_buffer_m,
        resolution_m=job.resolution_m,
    )
    if has_boundary_issue:
        logger.warning(
            "Buffer of %s m may be insufficient for afwateringseenheden tile %s",
            job.tile_buffer_m,
            tile.tile_id,
        )

    return AfwateringseenhedenTileResult(
        tile=tile,
        output_dir=tile_output_dir,
        rasters=rasters,
        subcatchments=subcatchment_result,
        usable_subcatchments=usable_subcatchments,
        has_boundary_issue=has_boundary_issue,
    )


def _calculate_tile_worker(
    job: AfwateringseenhedenTileJob,
) -> AfwateringseenhedenTileResult:
    """Calculate one tile in a spawned process and retain its full traceback."""
    try:
        return _calculate_tile(job)
    except Exception:
        raise AfwateringseenhedenTileError(
            job.tile.tile_id,
            traceback.format_exc(),
        ) from None


def _merge_subcatchments(
    subcatchments: Iterable[gpd.GeoDataFrame],
    *,
    gebied: BaseGeometry,
) -> gpd.GeoDataFrame:
    frames = [frame for frame in subcatchments if not frame.empty]
    if not frames:
        return gpd.GeoDataFrame(
            {
                "segment_fid": pd.Series(dtype="int64"),
                "segment_id": pd.Series(dtype="object"),
            },
            geometry=gpd.GeoSeries([], crs=None),
        )

    combined = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        geometry="geometry",
        crs=frames[0].crs,
    )
    merged = combined.dissolve(
        by="segment_id",
        as_index=False,
        aggfunc={"segment_fid": "first"},
    )
    merged = gpd.clip(merged, gebied)
    merged = merged[~merged.geometry.is_empty].copy()
    return merged[["segment_fid", "segment_id", "geometry"]].reset_index(drop=True)


def _write_merged_subcatchments(
    output_path: Path,
    subcatchments: gpd.GeoDataFrame,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _temporary_output_path(output_path)
    try:
        write_geopackage_layer(
            subcatchments,
            temporary_path,
            layer_name=SUBCATCHMENTS_LAYER,
            mode="w",
        )
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def calculate_afwateringseenheden_tiles(
    gebied: BaseGeometry,
    *,
    burn_depth_m: float,
    ahn_vrt_path: Path | None = None,
    watersysteem_path: Path | None = None,
    output_dir: Path | None = None,
    merged_output_path: Path | None = None,
    tiles_path: Path | None = None,
    data_store: DataStore | None = None,
    tile_ids: Collection[str] | None = None,
    tile_size_m: int = 5000,
    tile_buffer_m: float = 2000,
    origin_x: int = 0,
    origin_y: int = 0,
    resolution_m: float = 2.0,
    max_fill_depth_m: float = 50.0,
    overwrite: bool = False,
    engine: Literal["pcraster"] = "pcraster",
    workers: int | None = None,
) -> AfwateringseenhedenTilesResult:
    """Calculate afwateringseenheden for every tile intersecting an area.

    Parameters
    ----------
    gebied : shapely.geometry.base.BaseGeometry
        Project-CRS area used to select tiles and clip the merged result.
    burn_depth_m : float
        Burn depth passed to :func:`prepare_watersysteem_rasters`.
    ahn_vrt_path : Path, optional
        AHN VRT used for every tile. Defaults to the datastore AHN DTM VRT.
    watersysteem_path : Path, optional
        Prepared watersysteem GeoPackage. Defaults to the datastore output.
    output_dir : Path, optional
        Root directory for per-tile folders. Defaults to
        ``datastore.afwateringseenheden_path / 'tiles'``.
    merged_output_path : Path, optional
        GeoPackage path for the dissolved merged result. When omitted, no
        merged GeoPackage is written.
    tiles_path : Path, optional
        Existing tile-index GeoPackage. When omitted, a tile grid is generated
        directly from ``gebied`` using ``tile_size_m`` and the configured origin.
    data_store : waterlagen.datastore.DataStore, optional
        Datastore used for default input and output paths.
    tile_ids : Collection[str], optional
        Optional subset of selected tile IDs.
    tile_size_m : int, optional
        Tile width and height in metres, by default 5000.
    tile_buffer_m : float, optional
        Buffer around each tile used for the hydrological calculation, by
        default 2000.
    origin_x, origin_y : int, optional
        Origin of the generated tile grid, by default 0, 0.
    resolution_m : float, optional
        Raster resolution passed to :func:`prepare_watersysteem_rasters`.
    max_fill_depth_m : float, optional
        Maximum PCRaster depression fill depth in metres.
    overwrite : bool, optional
        Whether to regenerate existing per-tile rasters and subcatchments.
    engine : {"pcraster"}, optional
        Flow-direction engine.
    workers : int or None, optional
        Number of process workers used for independent tile calculations. When
        omitted, uses :attr:`waterlagen.settings.Settings.afwateringseenheden_workers`,
        which defaults to 1. A value of 1 keeps the calculation in the calling
        process.

    Returns
    -------
    AfwateringseenhedenTilesResult
        Per-tile results, skipped tile IDs, boundary issue tile IDs, and the
        in-memory merged GeoDataFrame.
    """
    _validate_tile_inputs(
        gebied,
        tile_size_m=tile_size_m,
        tile_buffer_m=tile_buffer_m,
        origin_x=origin_x,
        origin_y=origin_y,
    )
    data_store = data_store or default_datastore
    watersysteem_path = Path(
        watersysteem_path or data_store.afwateringseenheden_path / "watersysteem.gpkg"
    )
    output_dir = Path(output_dir or data_store.afwateringseenheden_path / "tiles")
    output_dir.mkdir(parents=True, exist_ok=True)

    tiles = (
        _read_intersecting_tiles(Path(tiles_path), gebied)
        if tiles_path is not None
        else _tiles_for_gebied(
            gebied,
            tile_size_m=tile_size_m,
            origin_x=origin_x,
            origin_y=origin_y,
        )
    )
    selected_tiles = _select_tiles(tiles, tile_ids)
    logger.info("Selected %s afwateringseenheden tile(s)", len(selected_tiles))

    worker_count = _resolve_worker_count(workers, tile_count=len(selected_tiles))
    logger.info(
        "Calculating %s afwateringseenheden tile(s) using %s worker(s)",
        len(selected_tiles),
        worker_count,
    )
    jobs = tuple(
        AfwateringseenhedenTileJob(
            tile=tile,
            output_dir=output_dir / tile.tile_id,
            burn_depth_m=burn_depth_m,
            ahn_vrt_path=Path(ahn_vrt_path) if ahn_vrt_path is not None else None,
            watersysteem_path=watersysteem_path,
            data_store=data_store,
            tile_buffer_m=tile_buffer_m,
            resolution_m=resolution_m,
            max_fill_depth_m=max_fill_depth_m,
            overwrite=overwrite,
            engine=engine,
        )
        for tile in selected_tiles
    )
    output_directories = {job.output_dir.resolve() for job in jobs}
    if len(output_directories) != len(jobs):
        raise ValueError(
            "Selected tiles must have unique tile IDs and output directories"
        )

    results_by_tile_id: dict[str, AfwateringseenhedenTileResult] = {}
    if worker_count == 1:
        for job in jobs:
            results_by_tile_id[job.tile.tile_id] = _calculate_tile(job)
    elif jobs:
        logger.info(
            "Submitting %s afwateringseenheden tile(s) with %s worker process(es)",
            len(jobs),
            worker_count,
        )
        failures: dict[str, BaseException] = {}
        spawn_context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(
            max_workers=worker_count,
            mp_context=spawn_context,
        ) as executor:
            futures = {
                executor.submit(_calculate_tile_worker, job): job for job in jobs
            }
            for future in as_completed(futures):
                job = futures[future]
                try:
                    results_by_tile_id[job.tile.tile_id] = future.result()
                    logger.info(
                        "Completed afwateringseenheden tile %s",
                        job.tile.tile_id,
                    )
                except Exception as exc:
                    failures[job.tile.tile_id] = exc
                    logger.exception(
                        "Failed afwateringseenheden tile %s",
                        job.tile.tile_id,
                    )

        if failures:
            ordered_failures = {
                job.tile.tile_id: failures[job.tile.tile_id]
                for job in jobs
                if job.tile.tile_id in failures
            }
            raise AfwateringseenhedenTilesError(ordered_failures)

    tile_results = [results_by_tile_id[job.tile.tile_id] for job in jobs]
    boundary_issue_tile_ids = [
        result.tile.tile_id for result in tile_results if result.has_boundary_issue
    ]
    skipped_tile_ids = [
        result.tile.tile_id
        for result in tile_results
        if result.skipped_reason is not None
    ]

    merged_subcatchments = _merge_subcatchments(
        (result.usable_subcatchments for result in tile_results),
        gebied=gebied,
    )
    merged_path = None
    if merged_output_path is not None and merged_subcatchments.empty:
        logger.warning(
            "No merged afwateringseenheden written because all selected tiles are empty"
        )
    elif merged_output_path is not None:
        merged_path = Path(merged_output_path)
        _write_merged_subcatchments(merged_path, merged_subcatchments)
        logger.info(
            "Wrote merged afwateringseenheden with %s feature(s) to %s",
            len(merged_subcatchments),
            merged_path,
        )

    return AfwateringseenhedenTilesResult(
        output_dir=output_dir,
        tile_results=tuple(tile_results),
        merged_path=merged_path,
        merged_subcatchments=merged_subcatchments,
        boundary_issue_tile_ids=tuple(boundary_issue_tile_ids),
        skipped_tile_ids=tuple(skipped_tile_ids),
    )
