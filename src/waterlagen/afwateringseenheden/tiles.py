"""Tile orchestration for afwateringseenheden calculations."""

import multiprocessing
import os
import tempfile
from collections.abc import Collection, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from math import ceil, floor, isfinite
from pathlib import Path
from typing import Literal

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from shapely import get_parts, union_all
from shapely.geometry import GeometryCollection, box
from shapely.geometry.base import BaseGeometry

from waterlagen import _geopandas as wgpd
from waterlagen import datastore as default_datastore
from waterlagen._crs import format_crs, same_crs
from waterlagen._geopackage import write_geopackage_layer
from waterlagen.datastore import DataStore
from waterlagen.logger import configure_logging, get_logger
from waterlagen.raster.tiles import Tile, read_tiles, tile_from_row
from waterlagen.settings import settings

from .pcraster import (
    SUBCATCHMENTS_FILENAME,
    SUBCATCHMENTS_GPKG_FILENAME,
    SUBCATCHMENTS_LAYER,
    SubcatchmentResult,
    calculate_subcatchments,
    require_pcraster,
)
from .raster import WatersysteemRasters, prepare_watersysteem_rasters

logger = get_logger(__name__)

# Numerical tolerance in square metres, not a minimum gap size.
_AREA_TOLERANCE = 0.0001


@dataclass(frozen=True, slots=True)
class AfwateringseenhedenTileResult:
    """Result for one afwateringseenheden tile calculation."""

    tile: Tile
    output_dir: Path
    rasters: WatersysteemRasters | None
    subcatchments: SubcatchmentResult | None
    usable_subcatchments: gpd.GeoDataFrame
    calculation_buffer_m: float
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
    gap_additions: gpd.GeoDataFrame | None = None
    remaining_gaps: gpd.GeoDataFrame | None = None


@dataclass
class _GapDonor:
    tile_id: str
    calculation_geometry: BaseGeometry
    subcatchments: gpd.GeoDataFrame


@dataclass
class _GapCandidate:
    tile_id: str
    subcatchments: gpd.GeoDataFrame
    coverage_area: float
    boundary_distance: float


@dataclass
class _GapFillResult:
    additions: gpd.GeoDataFrame
    remaining: gpd.GeoDataFrame


@dataclass(frozen=True, slots=True)
class _TileJob:
    """Explicit paths and settings passed to one independent tile calculation."""

    tile: Tile
    output_dir: Path
    ahn_vrt_path: Path
    watersysteem_path: Path
    burn_depth_m: float
    buffer_distances: tuple[float, ...]
    resolution_m: float
    max_fill_depth_m: float
    overwrite: bool
    engine: Literal["pcraster"]
    crs: str
    random_seed: int | None


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


def _calculation_buffer_distances(
    tile_buffer_m: float,
    retry_tile_buffer_m: Collection[float],
) -> tuple[float, ...]:
    """Return the initial buffer followed by progressively larger retries."""
    if isinstance(retry_tile_buffer_m, (str, bytes)):
        raise TypeError(
            "retry_tile_buffer_m must be a collection of numeric buffer distances"
        )

    retry_distances = tuple(float(distance) for distance in retry_tile_buffer_m)
    if any(
        not isfinite(distance) or distance <= tile_buffer_m
        for distance in retry_distances
    ):
        raise ValueError(
            "Each retry_tile_buffer_m value must be finite and greater than tile_buffer_m"
        )
    if tuple(sorted(retry_distances)) != retry_distances:
        raise ValueError("retry_tile_buffer_m values must be in ascending order")
    if len(set(retry_distances)) != len(retry_distances):
        raise ValueError("retry_tile_buffer_m values must not contain duplicates")
    return (tile_buffer_m, *retry_distances)


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
        return wgpd.read_file(path, layer=SUBCATCHMENTS_LAYER)
    except Exception as exc:
        logger.warning(
            "Existing afwateringseenheden tile output %s is invalid and will be replaced: %s",
            path,
            exc,
            exc_info=True,
        )
        return None


def _cached_buffer_m(job: _TileJob) -> float:
    """Read the actual cached buffer, including a previous larger-buffer retry."""
    raster_path = job.output_dir / SUBCATCHMENTS_FILENAME
    if not raster_path.is_file():
        raise FileNotFoundError(f"Cannot verify cached tile buffer: {raster_path}")
    with rasterio.open(raster_path) as raster:
        if not same_crs(raster.crs, job.crs) or raster.res != (
            job.resolution_m,
            job.resolution_m,
        ):
            raise ValueError(
                f"Cached grid CRS or resolution differs in tile {job.tile.tile_id}"
            )
        bounds = raster.bounds
    distances = (
        job.tile.xmin - bounds.left,
        job.tile.ymin - bounds.bottom,
        bounds.right - job.tile.xmax,
        bounds.top - job.tile.ymax,
    )
    if distances[0] < 0 or not all(
        isfinite(distance) and distance == distances[0] for distance in distances
    ):
        raise ValueError(
            f"Cached grid has an inconsistent buffer in tile {job.tile.tile_id}"
        )
    return distances[0]


def _polygonal_geometry(geometry: BaseGeometry) -> BaseGeometry:
    """Keep polygon parts, including those in nested geometry collections."""
    if geometry.geom_type in ("Polygon", "MultiPolygon"):
        return geometry
    if geometry.geom_type == "GeometryCollection":
        return union_all([_polygonal_geometry(part) for part in geometry.geoms])
    return GeometryCollection()


def _clean_polygon_geometries(subcatchments: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Remove line/point remnants without filling holes or moving polygon edges."""
    cleaned = subcatchments.loc[subcatchments.geometry.notna()].copy()
    cleaned.geometry = cleaned.geometry.map(_polygonal_geometry)
    return cleaned.loc[~cleaned.geometry.is_empty].reset_index(drop=True)


def _boundary_hits(
    subcatchments: gpd.GeoDataFrame,
    *,
    tile: Tile,
    tile_buffer_m: float,
    resolution_m: float,
) -> pd.Series:
    """Apply the same outer-boundary filter to core results and neighbour donors."""
    if tile_buffer_m == 0:
        return pd.Series(False, index=subcatchments.index)
    boundary_distance = max(tile_buffer_m - resolution_m, 0)
    boundary_geometry = (
        _tile_geometry(tile).buffer(boundary_distance, join_style="mitre").exterior
    )
    return subcatchments.geometry.intersects(boundary_geometry)


def _usable_subcatchments_for_tile(
    subcatchments: gpd.GeoDataFrame,
    *,
    tile: Tile,
    tile_buffer_m: float,
    resolution_m: float,
) -> tuple[gpd.GeoDataFrame, bool]:
    subcatchments = _clean_polygon_geometries(subcatchments)
    tile_geometry = _tile_geometry(tile)
    boundary_hits = _boundary_hits(
        subcatchments, tile=tile, tile_buffer_m=tile_buffer_m, resolution_m=resolution_m
    )

    boundary_issue = bool(
        subcatchments.loc[boundary_hits].geometry.intersects(tile_geometry).any()
    )
    usable = subcatchments.loc[~boundary_hits].copy()
    if usable.empty:
        return usable, boundary_issue

    clipped = gpd.clip(usable, tile_geometry)
    return _clean_polygon_geometries(clipped), boundary_issue


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
    if combined.groupby("segment_id").segment_fid.nunique().gt(1).any():
        raise ValueError("A segment_id has different segment_fid values across tiles")
    merged = combined.dissolve(
        by="segment_id",
        as_index=False,
        aggfunc={"segment_fid": "first"},
    )
    merged = gpd.clip(merged, gebied)
    merged = _clean_polygon_geometries(merged)
    return merged[["segment_fid", "segment_id", "geometry"]].reset_index(drop=True)


def _gap_donor(
    result: AfwateringseenhedenTileResult, *, resolution_m: float
) -> _GapDonor:
    """Reuse the raw tile polygons, retaining their usable buffer portions."""
    if result.subcatchments is not None:
        raw = result.subcatchments.subcatchments
    else:
        raw = wgpd.read_file(
            result.output_dir / SUBCATCHMENTS_GPKG_FILENAME, layer=SUBCATCHMENTS_LAYER
        )
    raw = _clean_polygon_geometries(raw)
    boundary_hits = _boundary_hits(
        raw,
        tile=result.tile,
        tile_buffer_m=result.calculation_buffer_m,
        resolution_m=resolution_m,
    )
    return _GapDonor(
        tile_id=result.tile.tile_id,
        calculation_geometry=_calculation_geometry(
            result.tile, tile_buffer_m=result.calculation_buffer_m
        ),
        subcatchments=raw.loc[~boundary_hits].copy(),
    )


def _fill_gap(
    gap: BaseGeometry, donors: Collection[_GapDonor]
) -> tuple[list[gpd.GeoDataFrame], BaseGeometry]:
    """Prefer most coverage, then most distance from the edge, then tile ID."""
    candidates = []
    for donor in donors:
        if not donor.calculation_geometry.intersects(gap):
            continue
        clipped = _clean_polygon_geometries(gpd.clip(donor.subcatchments, gap))
        if clipped.empty:
            continue
        coverage = clipped.geometry.union_all()
        candidates.append(
            _GapCandidate(
                tile_id=donor.tile_id,
                subcatchments=clipped,
                coverage_area=coverage.area,
                boundary_distance=coverage.distance(
                    donor.calculation_geometry.boundary
                ),
            )
        )
    candidates.sort(
        key=lambda candidate: (
            -candidate.coverage_area,
            -candidate.boundary_distance,
            candidate.tile_id,
        )
    )

    remaining = gap
    additions = []
    for priority, candidate in enumerate(candidates, start=1):
        if remaining.is_empty:
            break
        selected = _clean_polygon_geometries(
            gpd.clip(candidate.subcatchments, remaining)
        )
        if selected.empty:
            continue
        coverage = selected.geometry.union_all()
        if abs(selected.area.sum() - coverage.area) > _AREA_TOLERANCE:
            raise ValueError(f"Overlapping subcatchments in donor {candidate.tile_id}")
        selected["bron_tegel"] = candidate.tile_id
        selected["keuzevolgorde"] = priority
        additions.append(selected)
        remaining = remaining.difference(coverage)
    return additions, remaining


def _fill_gaps_from_neighbours(
    merged: gpd.GeoDataFrame,
    *,
    tile_results: Collection[AfwateringseenhedenTileResult],
    gebied: BaseGeometry,
    resolution_m: float,
) -> _GapFillResult:
    """Fill only uncovered parts of selected cores; never replace existing assignments."""
    crs = merged.crs or settings.crs
    spatial_index = merged.sindex
    ordered_results = sorted(tile_results, key=lambda result: result.tile.tile_id)
    donor_cache: dict[str, _GapDonor] = {}
    additions = []
    remaining_rows = []
    gap_id = 0
    missing_area = 0.0
    for result in ordered_results:
        area = _tile_geometry(result.tile).intersection(gebied)
        indices = spatial_index.query(area, predicate="intersects")
        occupied = merged.iloc[indices].geometry.intersection(area).union_all()
        missing = area.difference(occupied)
        missing_area += missing.area
        gaps = [part for part in get_parts(missing) if part.area > 0]
        if not gaps:
            continue
        logger.info(
            "Checking gaps in tile %s: %.4f ha",
            result.tile.tile_id,
            missing.area / 10000,
        )
        donors = []
        for neighbour in ordered_results:
            if (
                neighbour.tile.tile_id == result.tile.tile_id
                or neighbour.skipped_reason is not None
            ):
                continue
            calculation_geometry = _calculation_geometry(
                neighbour.tile, tile_buffer_m=neighbour.calculation_buffer_m
            )
            if calculation_geometry.intersection(missing).area == 0:
                continue
            tile_id = neighbour.tile.tile_id
            if tile_id not in donor_cache:
                donor_cache[tile_id] = _gap_donor(neighbour, resolution_m=resolution_m)
            donor = donor_cache[tile_id]
            if not same_crs(donor.subcatchments.crs, crs):
                raise ValueError(f"Donor tile {tile_id} has a different CRS")
            donors.append(donor)
        tile_additions = []
        for gap in sorted(gaps, key=lambda geometry: geometry.bounds):
            gap_id += 1
            filled, remaining = _fill_gap(gap, donors)
            for frame in filled:
                frame["doel_tegel"] = result.tile.tile_id
                frame["gat_id"] = gap_id
                tile_additions.append(frame)
            if remaining.area > 0:
                remaining_rows.append(
                    {
                        "doel_tegel": result.tile.tile_id,
                        "gat_id": gap_id,
                        "opp_m2": remaining.area,
                        "geometry": _polygonal_geometry(remaining),
                    }
                )
        if tile_additions:
            combined = gpd.GeoDataFrame(
                pd.concat(tile_additions, ignore_index=True), crs=crs
            )
            coverage = combined.geometry.union_all()
            if coverage.intersection(occupied).area > _AREA_TOLERANCE:
                raise ValueError("Gap additions overlap existing subcatchments")
            if coverage.difference(area).area > _AREA_TOLERANCE:
                raise ValueError("Gap additions extend outside the selected area")
            additions.append(combined)
            logger.info(
                "Filled gaps in tile %s: %.4f ha",
                result.tile.tile_id,
                coverage.area / 10000,
            )
    if additions:
        added = gpd.GeoDataFrame(pd.concat(additions, ignore_index=True), crs=crs)
        if abs(added.area.sum() - added.geometry.union_all().area) > _AREA_TOLERANCE:
            raise ValueError("Gap additions overlap one another")
    else:
        added = gpd.GeoDataFrame(
            columns=[
                "segment_fid",
                "segment_id",
                "bron_tegel",
                "keuzevolgorde",
                "doel_tegel",
                "gat_id",
                "geometry",
            ],
            geometry="geometry",
            crs=crs,
        )
    added["opp_m2"] = added.area
    remaining = gpd.GeoDataFrame(
        remaining_rows,
        columns=["doel_tegel", "gat_id", "opp_m2", "geometry"],
        geometry="geometry",
        crs=crs,
    )
    if abs(missing_area - added.area.sum() - remaining.area.sum()) > _AREA_TOLERANCE:
        raise ValueError("Gap filling changed the area balance")
    logger.info(
        "Gap filling complete: %.4f ha added, %.4f ha remain without a usable neighbour",
        added.area.sum() / 10000,
        remaining.area.sum() / 10000,
    )
    return _GapFillResult(added, remaining)


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
        written = wgpd.read_file(temporary_path, layer=SUBCATCHMENTS_LAYER)
        if len(written) != len(subcatchments) or not written.is_valid.all():
            raise ValueError(f"Invalid written layer {SUBCATCHMENTS_LAYER}")
        if not written.geom_type.isin(["Polygon", "MultiPolygon"]).all():
            raise ValueError(
                f"Non-polygon geometry in written layer {SUBCATCHMENTS_LAYER}"
            )
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _calculate_tile(job: _TileJob) -> AfwateringseenhedenTileResult:
    """Calculate or reuse one tile, retrying only when configured."""
    tile = job.tile
    job.output_dir.mkdir(parents=True, exist_ok=True)
    buffer_distances = job.buffer_distances
    existing_subcatchments = None
    if not job.overwrite:
        existing_subcatchments = _read_existing_subcatchments(
            job.output_dir / SUBCATCHMENTS_GPKG_FILENAME
        )
        if existing_subcatchments is not None:
            cached_buffer = _cached_buffer_m(job)
            larger_retries = [
                distance
                for distance in buffer_distances[1:]
                if distance > cached_buffer
            ]
            buffer_distances = (cached_buffer, *larger_retries)
    for attempt, calculation_buffer_m in enumerate(buffer_distances):
        logger.info(
            "Calculating afwateringseenheden tile %s with a %s m buffer",
            tile.tile_id,
            calculation_buffer_m,
        )
        if attempt > 0:
            existing_subcatchments = None

        if existing_subcatchments is None:
            rasters = prepare_watersysteem_rasters(
                _calculation_geometry(tile, tile_buffer_m=calculation_buffer_m),
                burn_depth_m=job.burn_depth_m,
                ahn_vrt_path=job.ahn_vrt_path,
                watersysteem_path=job.watersysteem_path,
                output_dir=job.output_dir,
                resolution_m=job.resolution_m,
                overwrite=job.overwrite or attempt > 0,
            )
            if not _has_segment_cells(rasters):
                logger.info(
                    "Skipping afwateringseenheden tile %s without hydroobject segments",
                    tile.tile_id,
                )
                return AfwateringseenhedenTileResult(
                    tile=tile,
                    output_dir=job.output_dir,
                    rasters=rasters,
                    subcatchments=None,
                    usable_subcatchments=_empty_like_subcatchments(None),
                    calculation_buffer_m=calculation_buffer_m,
                    skipped_reason="no hydroobject_segment cells",
                )
            if job.random_seed is not None:
                require_pcraster().setrandomseed(job.random_seed)
            subcatchment_result = calculate_subcatchments(
                rasters,
                watersysteem_path=job.watersysteem_path,
                max_fill_depth_m=job.max_fill_depth_m,
                engine=job.engine,
            )
            subcatchments = subcatchment_result.subcatchments
        else:
            rasters = WatersysteemRasters(
                dem_path=job.output_dir / "dem_2m.tif",
                hydroobject_segment_path=job.output_dir / "hydroobject_segment.tif",
            )
            subcatchment_result = None
            subcatchments = existing_subcatchments
            logger.info("Reusing afwateringseenheden tile %s", tile.tile_id)

        usable_subcatchments, has_boundary_issue = _usable_subcatchments_for_tile(
            subcatchments,
            tile=tile,
            tile_buffer_m=calculation_buffer_m,
            resolution_m=job.resolution_m,
        )
        if has_boundary_issue and attempt < len(buffer_distances) - 1:
            logger.warning(
                "Buffer of %s m is insufficient for afwateringseenheden tile %s; retrying with %s m",
                calculation_buffer_m,
                tile.tile_id,
                buffer_distances[attempt + 1],
            )
            continue
        if has_boundary_issue:
            logger.warning(
                "Buffer of %s m may be insufficient for afwateringseenheden tile %s",
                calculation_buffer_m,
                tile.tile_id,
            )
        return AfwateringseenhedenTileResult(
            tile=tile,
            output_dir=job.output_dir,
            rasters=rasters,
            subcatchments=subcatchment_result,
            usable_subcatchments=usable_subcatchments,
            calculation_buffer_m=calculation_buffer_m,
            has_boundary_issue=has_boundary_issue,
        )
    raise ValueError("A tile calculation requires at least one buffer distance")


def _calculate_tile_worker(job: _TileJob) -> AfwateringseenhedenTileResult:
    """Open data in a separate process; keep worker logs in its own tile folder."""
    job.output_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(log_file=job.output_dir / "workflow.log", stdout=False)
    settings.crs = job.crs
    with rasterio.Env(
        GDAL_NUM_THREADS="1", VRT_NUM_THREADS="1", GDAL_CACHEMAX=256 * 1024 * 1024
    ):
        return _calculate_tile(job)


def _calculate_tiles_parallel(
    jobs: list[_TileJob], workers: int
) -> list[AfwateringseenhedenTileResult]:
    """Collect worker results in tile order; never merge a partially failed run."""
    if not jobs:
        return []
    results: dict[str, AfwateringseenhedenTileResult] = {}
    failures: dict[str, str] = {}
    logger.info("Calculating %s tiles with %s worker processes", len(jobs), workers)
    with ProcessPoolExecutor(
        max_workers=min(workers, len(jobs)),
        mp_context=multiprocessing.get_context("spawn"),
    ) as executor:
        futures = {executor.submit(_calculate_tile_worker, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                failures[job.tile.tile_id] = str(exc)
                logger.exception("Failed afwateringseenheden tile %s", job.tile.tile_id)
                continue
            results[job.tile.tile_id] = result
            logger.info(
                "Completed tile %s (%s/%s), buffer %s m, boundary issue: %s, skipped: %s",
                job.tile.tile_id,
                len(results),
                len(jobs),
                result.calculation_buffer_m,
                result.has_boundary_issue,
                result.skipped_reason,
            )
    if failures:
        details = "; ".join(
            f"{tile_id}: {error}" for tile_id, error in failures.items()
        )
        raise RuntimeError(
            f"Failed afwateringseenheden tiles; merged output not written: {details}"
        )
    return [results[job.tile.tile_id] for job in jobs]


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
    retry_tile_buffer_m: Collection[float] = (),
    origin_x: int = 0,
    origin_y: int = 0,
    resolution_m: float = 2.0,
    max_fill_depth_m: float = 50.0,
    overwrite: bool = False,
    engine: Literal["pcraster"] = "pcraster",
    workers: int = 1,
    random_seed: int | None = None,
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
        merged GeoPackage is written. An existing merged file is replaced
        after success, independently of ``overwrite``; choose a new path
        to retain previous merged results. Worker failures prevent merging.
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
    retry_tile_buffer_m : Collection[float], optional
        Progressively larger buffer distances in metres. A tile is recalculated
        with these buffers when an afwateringseenheid reaches the calculation
        boundary. The default performs no retries.
    origin_x, origin_y : int, optional
        Origin of the generated tile grid, by default 0, 0.
    resolution_m : float, optional
        Raster resolution passed to :func:`prepare_watersysteem_rasters`.
    max_fill_depth_m : float, optional
        Maximum PCRaster depression fill depth in metres.
    overwrite : bool, optional
        Whether to regenerate existing per-tile rasters and subcatchments.
        Cached raster metadata determines the actual buffer, including a previous
        retry. Cached CRS and resolution must match the requested grid.
        Reusing a tile requires its ``subcatchments.tif`` alongside the GeoPackage.
    engine : {"pcraster"}, optional
        Flow-direction engine.
    workers : int, optional
        Number of separate worker processes. The default of 1 runs serially.
        Workers open their own inputs and write only to their tile folder,
        including a ``workflow.log``. Results are merged in selection order.
        Run parallel workflows from a script with a ``__main__`` guard.
    random_seed : int, optional
        Positive PCRaster seed reset before each fresh tile calculation.
        Use the same seed for reproducible serial and parallel runs. The
        default leaves PCRaster's random state unchanged; cached results
        are reused independently of this setting when ``overwrite=False``.

    Returns
    -------
    AfwateringseenhedenTilesResult
        Per-tile results, skipped tile IDs, boundary issue tile IDs, and the
        in-memory merged GeoDataFrame.

    Notes
    -----
    Line and point remnants from clipping are removed. After merging the core
    results, uncovered parts of selected tiles are filled from usable neighbour
    buffer polygons. Polygons touching their calculation boundary are excluded.
    Donors are ranked by coverage, distance from their outer boundary, and tile
    ID. Existing assignments are retained. This step performs no new LDD work.
    ``gap_additions`` and ``remaining_gaps`` report the changes and unfilled area
    in memory. Only the merged subcatchments are written to the GeoPackage. Boundary issue
    tile IDs still describe the original calculations, not the remaining gaps.
    """
    if not isinstance(workers, int) or isinstance(workers, bool):
        raise TypeError("workers must be an integer")
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if random_seed is not None:
        if not isinstance(random_seed, int) or isinstance(random_seed, bool):
            raise TypeError("random_seed must be an integer or None")
        if random_seed < 1:
            raise ValueError("random_seed must be positive")
    _validate_tile_inputs(
        gebied,
        tile_size_m=tile_size_m,
        tile_buffer_m=tile_buffer_m,
        origin_x=origin_x,
        origin_y=origin_y,
    )
    calculation_buffer_distances = _calculation_buffer_distances(
        tile_buffer_m,
        retry_tile_buffer_m,
    )
    data_store = data_store or default_datastore
    ahn_vrt_path = Path(ahn_vrt_path or data_store.ahn_dir / "dtm_05" / "dtm_05.vrt")
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
    if len({tile.tile_id for tile in selected_tiles}) != len(selected_tiles):
        raise ValueError("Selected tiles must have unique tile IDs")
    logger.info("Selected %s afwateringseenheden tile(s)", len(selected_tiles))

    jobs = [
        _TileJob(
            tile=tile,
            output_dir=output_dir / tile.tile_id,
            ahn_vrt_path=ahn_vrt_path,
            watersysteem_path=watersysteem_path,
            burn_depth_m=burn_depth_m,
            buffer_distances=calculation_buffer_distances,
            resolution_m=resolution_m,
            max_fill_depth_m=max_fill_depth_m,
            overwrite=overwrite,
            engine=engine,
            crs=format_crs(settings.crs),
            random_seed=random_seed,
        )
        for tile in selected_tiles
    ]
    if workers == 1:
        tile_results = [_calculate_tile(job) for job in jobs]
    else:
        for path in (ahn_vrt_path, watersysteem_path):
            if not path.is_file():
                raise FileNotFoundError(path)
        tile_results = _calculate_tiles_parallel(jobs, workers)

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
    gap_fill = _fill_gaps_from_neighbours(
        merged_subcatchments,
        tile_results=tile_results,
        gebied=gebied,
        resolution_m=resolution_m,
    )
    if not gap_fill.additions.empty:
        expected_area = merged_subcatchments.area.sum() + gap_fill.additions.area.sum()
        merged_subcatchments = _merge_subcatchments(
            [merged_subcatchments, gap_fill.additions], gebied=gebied
        )
        if abs(merged_subcatchments.area.sum() - expected_area) > _AREA_TOLERANCE:
            raise ValueError("Merging gap additions changed existing coverage")
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
        gap_additions=gap_fill.additions,
        remaining_gaps=gap_fill.remaining,
    )
