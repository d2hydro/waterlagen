"""Core-only DEM tiles, reusable building heights and ordered VRT/COG assembly."""

import json
import sqlite3
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ProcessPoolExecutor,
    as_completed,
    wait,
)
from contextlib import closing, nullcontext
from dataclasses import asdict, dataclass
from math import ceil
from multiprocessing import get_context
from pathlib import Path
from time import monotonic
from uuid import uuid4

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask, shapes
from rasterio.windows import Window
from shapely.geometry import box, shape
from tqdm.auto import tqdm

from waterlagen import _geopandas as wgpd
from waterlagen._crs import same_crs
from waterlagen._filesystem import replace_file
from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._production import _file_identity
from waterlagen.administratieve_gebieden import read_landsgrens
from waterlagen.ahn import interpolate
from waterlagen.areas import resolve_workers
from waterlagen.functioneel_landgebruik.gebouwen import (
    building_paths,
    validate_buildings,
)
from waterlagen.functioneel_landgebruik.paths import source_path
from waterlagen.logger import get_logger, tile_logging
from waterlagen.raster.overviews import build_raster_overviews
from waterlagen.raster.tiles import _tile_id
from waterlagen.raster.vrt import create_cog_file, create_vrt_file
from waterlagen.settings import settings

from .config import DemConfig
from .exports import create_float_dem
from .gebouwen import aligned_window, calculate_building_elevations

logger = get_logger(__name__)
VERSION = "2"
WATER_CODES = (100, 228)
DIAGNOSTICS_VERSION = 1


@dataclass
class _CoverageCounts:
    """Disjoint categories of missing DEM cells after the building overlay."""

    outside_landgebied: int = 0
    open_water: int = 0
    inside_landgebied_nonwater: int = 0


def _check_coverage(
    paths: list["DemTilePaths"], landuse_tiles: list[Path], landgebied_path: Path | None
) -> _CoverageCounts:
    """Report remaining gaps in the final DEM without blocking publication.

    Boundary membership follows pixel centres. Without a boundary, all tile
    cores are counted as landgebied. Unknown land-use cells count as non-water.
    """
    land = None
    if landgebied_path is not None:
        boundary = read_landsgrens(path=landgebied_path)
        if boundary.crs is None or boundary.empty:
            raise ValueError("landgebied requires a CRS and nonempty geometry")
        if not same_crs(boundary.crs, settings.crs):
            boundary = boundary.to_crs(settings.crs)
        land = boundary.geometry.make_valid().union_all()
        if land.is_empty or land.area <= 0:
            raise ValueError("landgebied has no polygon area")
    counts = _CoverageCounts()
    cell_area_m2 = 0.0
    for tile_paths, landuse_path in tqdm(
        zip(paths, landuse_tiles, strict=True),
        total=len(paths),
        desc="DEM NoData-controle",
        unit="tegel",
    ):
        with (
            rasterio.open(tile_paths.terrain) as terrain,
            rasterio.open(tile_paths.buildings) as buildings,
            rasterio.open(landuse_path) as landuse,
        ):
            cell_area_m2 = abs(terrain.transform.a * terrain.transform.e)
            if (landuse.shape, landuse.transform, landuse.crs) != (
                terrain.shape,
                terrain.transform,
                terrain.crs,
            ):
                raise ValueError("Land-use and DEM coverage grids differ")
            inside = None
            if land is not None:
                clipped = land.intersection(box(*terrain.bounds))
                inside = (
                    geometry_mask(
                        [clipped],
                        out_shape=terrain.shape,
                        transform=terrain.transform,
                        invert=True,
                        all_touched=False,
                    )
                    if clipped.area > 0
                    else np.zeros(terrain.shape, dtype=bool)
                )
            for _, window in terrain.block_windows(1):
                base = terrain.read(1, window=window, masked=True)
                overlay = buildings.read(1, window=window, masked=True)
                valid_base = ~np.ma.getmaskarray(base) & np.isfinite(base.data)
                valid_overlay = ~np.ma.getmaskarray(overlay) & np.isfinite(overlay.data)
                missing = ~(valid_base | valid_overlay)
                if not missing.any():
                    continue
                if inside is not None:
                    local_land = inside[window.toslices()]
                    counts.outside_landgebied += int(
                        np.count_nonzero(missing & ~local_land)
                    )
                    missing &= local_land
                water = np.isin(landuse.read(1, window=window), WATER_CODES)
                counts.open_water += int(np.count_nonzero(missing & water))
                counts.inside_landgebied_nonwater += int(
                    np.count_nonzero(missing & ~water)
                )
    logger.info(
        "DEM NoData: %s buiten landgebied; %s in open water; "
        "%s binnen landgebied anders dan water; publicatie gaat door",
        counts.outside_landgebied,
        counts.open_water,
        counts.inside_landgebied_nonwater,
    )
    logger.info(
        "DEM NoData-oppervlak: %.3f km2 buiten landgebied; %.3f km2 in water; "
        "%.3f km2 in overig landgebruik binnen landgebied",
        counts.outside_landgebied * cell_area_m2 / 1e6,
        counts.open_water * cell_area_m2 / 1e6,
        counts.inside_landgebied_nonwater * cell_area_m2 / 1e6,
    )
    return counts


def _save_json(path: Path, content: dict) -> None:
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(
        json.dumps(content, sort_keys=True, indent=2), encoding="utf-8"
    )
    replace_file(temporary, path)


def _validate_grid(
    ahn: rasterio.io.DatasetReader, reference: rasterio.io.DatasetReader
) -> None:
    if not same_crs(ahn.crs, settings.crs) or not same_crs(ahn.crs, reference.crs):
        raise ValueError("AHN, land-use and project CRS must agree")
    if ahn.count != 1 or ahn.transform.b or ahn.transform.d or ahn.res[0] != ahn.res[1]:
        raise ValueError("DEM requires a north-up single-band square AHN grid")
    if (
        reference.count != 1
        or reference.transform.b
        or reference.transform.d
        or reference.transform.a <= 0
        or reference.transform.e >= 0
    ):
        raise ValueError("Land-use tiles must have a north-up single-band grid")
    if not np.allclose(ahn.res, reference.res, rtol=0, atol=1e-9):
        raise ValueError(
            "AHN and land-use resolution differ; resampling is not implicit"
        )
    col, row = (~ahn.transform) * (reference.transform.c, reference.transform.f)
    if not np.allclose([col, row], np.rint([col, row]), rtol=0, atol=1e-7):
        raise ValueError("AHN and land-use pixel origins differ")
    if (
        not np.isfinite(ahn.scales[0])
        or ahn.scales[0] <= 0
        or not np.isfinite(ahn.offsets[0])
    ):
        raise ValueError("AHN scale must be positive and offset finite")


def _read_buildings(
    tiles: list[Path], context_m: float
) -> tuple[gpd.GeoDataFrame, set[int]]:
    records = []
    selected = set()
    for tile in tiles:
        validate_buildings(tile, context_m)
        ids_path, geometries_path = building_paths(tile)
        records.append(
            wgpd.read_file(geometries_path, layer="gebouwen")[
                ["gebouw_id", "identificatie", "geometry"]
            ]
        )
        with rasterio.open(ids_path) as ids:
            for _, window in ids.block_windows(1):
                selected.update(
                    int(value)
                    for value in np.unique(ids.read(1, window=window))
                    if value
                )
    buildings = gpd.GeoDataFrame(
        pd.concat(records, ignore_index=True), crs=records[0].crs
    )
    buildings["geometry_key"] = buildings.geometry.to_wkb()
    conflicts = buildings.groupby("gebouw_id")[
        ["identificatie", "geometry_key"]
    ].nunique()
    if (conflicts > 1).any().any():
        raise ValueError("Building identity/complete geometry differs between tiles")
    buildings = buildings.drop_duplicates("gebouw_id").drop(columns="geometry_key")
    return buildings.sort_values("gebouw_id").reset_index(drop=True), selected


def _nodata(source: rasterio.io.DatasetReader) -> float:
    if source.nodata is not None:
        return source.nodata
    if np.issubdtype(np.dtype(source.dtypes[0]), np.floating):
        return float("nan")
    raise ValueError("Integer AHN must declare a NoData value")


def _write_tile(
    path: Path,
    values: np.ndarray,
    source: rasterio.io.DatasetReader,
    transform,
    config: DemConfig,
    pair: str,
    *,
    provenance: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.tif")
    profile = {
        "driver": "GTiff",
        "count": 1,
        "dtype": str(values.dtype),
        "nodata": 0 if provenance else _nodata(source),
        "width": values.shape[1],
        "height": values.shape[0],
        "transform": transform,
        "crs": source.crs,
        "tiled": True,
        "blockxsize": config.output.block_size,
        "blockysize": config.output.block_size,
        "compress": "ZSTD",
        "bigtiff": "IF_SAFER",
    }
    try:
        with rasterio.open(temporary, "w", **profile) as dst:
            dst.write(values, 1)
            if not provenance:
                dst.scales, dst.offsets = source.scales, source.offsets
            dst.update_tags(dem_version=VERSION, output_pair=pair)
            build_raster_overviews(
                dst,
                factors=config.output.overview_factors,
                resampling=Resampling.nearest if provenance else Resampling.average,
            )
        with rasterio.open(temporary) as check:
            for _, window in check.block_windows(1):
                if not np.array_equal(
                    check.read(1, window=window),
                    values[window.toslices()],
                    equal_nan=True,
                ):
                    raise ValueError(f"DEM tile validation failed: {path}")
        replace_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _stored_height(height: float, source: rasterio.io.DatasetReader):
    value = (height - source.offsets[0]) / source.scales[0]
    dtype = np.dtype(source.dtypes[0])
    if np.issubdtype(dtype, np.integer):
        value = np.rint(value)
        limits = np.iinfo(dtype)
        if not limits.min <= value <= limits.max:
            raise ValueError("Building elevation exceeds AHN storage range")
    stored = np.asarray(value, dtype=dtype).item()
    if not np.isfinite(stored) or stored == source.nodata:
        raise ValueError("Building elevation conflicts with AHN NoData")
    return stored


@dataclass(frozen=True, slots=True)
class DemTilePaths:
    """The products of one core, stored together in a coordinate tile folder."""

    terrain: Path
    buildings: Path
    provenance: Path
    diagnostics: Path
    ahn_provenance: Path

    @property
    def files(self) -> tuple[Path, ...]:
        return (*self.rasters, self.diagnostics)

    @property
    def rasters(self) -> tuple[Path, ...]:
        return self.terrain, self.buildings, self.provenance, self.ahn_provenance


def _tile_paths(output: Path, tile: Path) -> DemTilePaths:
    with rasterio.open(tile) as reference:
        bounds = tuple(reference.bounds)
    if not all(value == round(value) for value in bounds):
        raise ValueError("DEM tile bounds must be whole-metre coordinates")
    tile_id = _tile_id(*(int(value) for value in bounds))
    folder = output / "tiles" / tile_id
    return DemTilePaths(
        folder / "ahn_aangevuld.tif",
        folder / "gebouwhoogten.tif",
        folder / "dem_bron.tif",
        folder / "nodata.gpkg",
        folder / "ahn_bron.tif",
    )


def _reuse_tile(
    paths: DemTilePaths,
    marker: Path,
    reference: rasterio.io.DatasetReader,
) -> bool:
    if not marker.is_file() or not all(path.is_file() for path in paths.rasters):
        return False
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    for path in paths.rasters:
        try:
            with rasterio.open(path) as src:
                if src.tags().get("output_pair") != metadata["output_pair"] or (
                    src.shape,
                    src.transform,
                    src.crs,
                ) != (reference.shape, reference.transform, reference.crs):
                    return False
                for _, window in src.block_windows(1):
                    src.read(1, window=window)
        except rasterio.errors.RasterioError:
            return False
    return True


def _diagnostics(records: list[dict], crs) -> gpd.GeoDataFrame:
    columns = [
        "bron",
        "categorie",
        "reden",
        "identificatie",
        "gebouw_id",
        "zoekafstand_m",
        "donor_aantal",
        "geometry",
    ]
    result = gpd.GeoDataFrame(records, columns=columns, geometry="geometry", crs=crs)
    result["zoekafstand_m"] = pd.to_numeric(result.zoekafstand_m).astype("float64")
    for name in ("gebouw_id", "donor_aantal"):
        result[name] = pd.to_numeric(result[name]).astype("Int64")
    return result


def _refresh_tile_diagnostics(
    tile: Path, paths: DemTilePaths, heights: pd.DataFrame, config: DemConfig
) -> None:
    """Rebuild versioned diagnostics from stored terrain, without recomputation.

    AHN gaps are measured after interpolation and before the building overlay.
    Polygonization splits water and other land use exactly along cell edges.
    """
    _, footprints = building_paths(tile)
    marker = paths.diagnostics.with_name("diagnostics.json")
    identity = {
        "version": DIAGNOSTICS_VERSION,
        "inputs": [
            _file_identity(p)
            for p in (paths.terrain, paths.buildings, tile, footprints)
        ],
        "search_distance_m": config.interpolation_max_distance_m,
    }
    if marker.exists() and paths.diagnostics.exists():
        previous = json.loads(marker.read_text(encoding="utf-8"))
        if previous == {**identity, "output": _file_identity(paths.diagnostics)}:
            return
    logger.info("NoData-categorieen samenstellen: %s", paths.terrain.parent.name)
    records = []
    with rasterio.open(paths.terrain) as terrain, rasterio.open(tile) as landuse:
        if (terrain.shape, terrain.transform, terrain.crs) != (
            landuse.shape,
            landuse.transform,
            landuse.crs,
        ):
            raise ValueError("Land-use and terrain diagnostic grids differ")
        classes = np.zeros(terrain.shape, dtype="uint8")
        for _, window in terrain.block_windows(1):
            values = terrain.read(1, window=window, masked=True)
            missing = np.ma.getmaskarray(values) | ~np.isfinite(values.data)
            if missing.any():
                water = np.isin(landuse.read(1, window=window), WATER_CODES)
                classes[window.toslices()] = np.where(missing, np.where(water, 1, 2), 0)
        for geometry, category in shapes(
            classes, mask=classes > 0, transform=terrain.transform
        ):
            records.append(
                {
                    "bron": "AHN",
                    "categorie": "AHN_water" if category == 1 else "AHN_overig",
                    "reden": "Geen geldige AHN-hoogte binnen interpolatieafstand",
                    "identificatie": None,
                    "gebouw_id": None,
                    "zoekafstand_m": config.interpolation_max_distance_m,
                    "donor_aantal": 0,
                    "geometry": shape(geometry),
                }
            )
        failed = heights[heights.hoogte_m.isna()].set_index("gebouw_id")
        if not failed.empty:
            geometries = _height_rows(footprints, set(failed.index))
            for row in geometries.itertuples():
                estimate = failed.loc[row.gebouw_id]
                records.append(
                    {
                        "bron": "Gebouw",
                        "categorie": "Gebouw",
                        "reden": "Geen oorspronkelijke AHN-donor binnen maximale gebouwzoekafstand",
                        "identificatie": row.identificatie,
                        "gebouw_id": row.gebouw_id,
                        "zoekafstand_m": estimate.zoekafstand_m,
                        "donor_aantal": estimate.donor_aantal,
                        "geometry": row.geometry,
                    }
                )
        write_geopackage_layer_atomically(
            _diagnostics(records, terrain.crs), paths.diagnostics, layer_name="nodata"
        )
    _save_json(marker, {**identity, "output": _file_identity(paths.diagnostics)})


def _build_tile(
    tile: Path,
    ahn: rasterio.io.DatasetReader,
    heights: pd.DataFrame,
    output: Path,
    config: DemConfig,
    overwrite: bool,
) -> DemTilePaths:
    paths = _tile_paths(output, tile)
    marker = paths.terrain.parent / "status.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(tile) as reference:
        _validate_grid(ahn, reference)
        if not overwrite and _reuse_tile(paths, marker, reference):
            logger.info("Reusing DEM tile %s", paths.terrain.parent.name)
            _refresh_tile_diagnostics(tile, paths, heights, config)
            return paths
        marker.unlink(missing_ok=True)
        core = aligned_window(tuple(reference.bounds), ahn.transform)
        margin = ceil(config.interpolation_max_distance_m / ahn.res[0]) + 1
        work = Window(
            core.col_off - margin,
            core.row_off - margin,
            core.width + 2 * margin,
            core.height + 2 * margin,
        )
        raw = ahn.read(1, window=work, boundless=True, masked=True)
        valid = ~np.ma.getmaskarray(raw) & np.isfinite(raw.data)
        result = interpolate.interpolate_masked(
            raw.data,
            target_mask=~valid,
            donor_mask=valid,
            max_distance_m=config.interpolation_max_distance_m,
            pixel_width=ahn.res[0],
            pixel_height=ahn.res[1],
        )
        crop = np.s_[
            margin : margin + reference.height, margin : margin + reference.width
        ]
        filled = result.filled_mask[crop]
        terrain = result.values[crop].copy()
        original = valid[crop]
        terrain[~original & ~filled] = _nodata(ahn)
        del raw, result, valid
        provenance = np.zeros(terrain.shape, dtype="uint8")
        provenance[original] = 1
        provenance[filled] = 3
        ahn_provenance = provenance.copy()
        ids_path, _ = building_paths(tile)
        with rasterio.open(ids_path) as ids_src:
            ids = ids_src.read(1)
        building = ids > 0
        building_values = np.full(terrain.shape, _nodata(ahn), dtype=terrain.dtype)
        lookup = heights.set_index("gebouw_id")
        # Map only the building pixels, avoiding one full-tile comparison per pand.
        unique, inverse = np.unique(ids[building], return_inverse=True)
        stored = np.full(len(unique), _nodata(ahn), dtype=terrain.dtype)
        resolved = np.zeros(len(unique), dtype=bool)
        for index, building_id in enumerate(unique):
            elevation = lookup.at[int(building_id), "hoogte_m"]
            if pd.notna(elevation):
                stored[index] = _stored_height(float(elevation), ahn)
                resolved[index] = True
        building_values[building] = stored[inverse]
        # Failed building estimates leave the underlying terrain intact.
        provenance[building] = np.where(resolved[inverse], 2, provenance[building])
        missing_ahn = provenance == 0
        pair = uuid4().hex
        _write_tile(paths.terrain, terrain, ahn, reference.transform, config, pair)
        _write_tile(
            paths.buildings, building_values, ahn, reference.transform, config, pair
        )
        _write_tile(
            paths.provenance,
            provenance,
            ahn,
            reference.transform,
            config,
            pair,
            provenance=True,
        )
        _write_tile(
            paths.ahn_provenance,
            ahn_provenance,
            ahn,
            reference.transform,
            config,
            pair,
            provenance=True,
        )
        _save_json(
            marker,
            {
                "output_pair": pair,
                "version": VERSION,
                "missing_cells": int(missing_ahn.sum()),
            },
        )
        logger.info(
            "DEM tile %s: %s original, %s interpolated, %s building, %s unresolved",
            paths.terrain.parent.name,
            int((provenance == 1).sum()),
            int((provenance == 3).sum()),
            int((provenance == 2).sum()),
            int((provenance == 0).sum()),
        )
        _refresh_tile_diagnostics(tile, paths, heights, config)
    return paths


def _height_rows(path: Path, ids: set[int], *, geometry: bool = True) -> pd.DataFrame:
    """Read only a tile's IDs, avoiding national tables in worker memory."""
    chunks = []
    ordered = sorted(ids)
    for start in range(0, len(ordered), 900):
        clause = ",".join(str(value) for value in ordered[start : start + 900])
        chunks.append(
            wgpd.read_file(
                path,
                layer="gebouwen",
                where=f"gebouw_id IN ({clause})",
                read_geometry=geometry,
            )
        )
    if not chunks:
        return wgpd.read_file(
            path, layer="gebouwen", where="1=0", read_geometry=geometry
        )
    return pd.concat(chunks, ignore_index=True)


def _check_height_identity(buildings: gpd.GeoDataFrame, cached: pd.DataFrame) -> None:
    """Require identical identities and complete footprints across tile borders."""
    expected = buildings.set_index("gebouw_id").loc[cached.gebouw_id]
    if (
        expected.identificatie.astype(str).tolist()
        != cached.identificatie.astype(str).tolist()
        or expected.geometry.to_wkb().tolist() != cached.geometry.to_wkb().tolist()
    ):
        raise ValueError("Building identity/complete geometry differs between tiles")


def _append_heights(target: Path, heights: gpd.GeoDataFrame) -> int:
    """Merge a completed batch in the coordinator, including interrupted retries."""
    if heights.gebouw_id.duplicated().any():
        raise ValueError("Duplicate building IDs in height batch")
    if target.exists():
        cached = _height_rows(target, set(heights.gebouw_id))
        _check_height_identity(heights, cached)
        columns = ["hoogte_m", "zoekafstand_m", "donor_aantal"]
        expected = heights.set_index("gebouw_id").loc[cached.gebouw_id, columns]
        if not np.array_equal(
            expected.to_numpy(dtype=float),
            cached[columns].to_numpy(dtype=float),
            equal_nan=True,
        ):
            raise ValueError("Conflicting cached building elevations")
        heights = heights[~heights.gebouw_id.isin(cached.gebouw_id)]
        if heights.empty:
            return 0
    heights.to_file(
        target,
        layer="gebouwen",
        driver="GPKG",
        index=False,
        mode="a" if target.exists() else "w",
    )
    with closing(sqlite3.connect(target)) as connection:
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS gebouw_id_lookup ON gebouwen (gebouw_id)"
        )
        connection.commit()
    return len(heights)


@dataclass
class _HeightBatch:
    """One exclusively assigned set of buildings and its full donor context."""

    buildings: gpd.GeoDataFrame
    selected_ids: set[int]
    ahn_path: Path
    output: Path
    config: DemConfig


def _height_batch_worker(batch: _HeightBatch) -> Path:
    with (
        tile_logging(batch.output.with_suffix(".log")),
        rasterio.open(batch.ahn_path) as ahn,
    ):
        heights = calculate_building_elevations(
            batch.buildings, batch.selected_ids, ahn, batch.config
        )
        write_geopackage_layer_atomically(heights, batch.output, layer_name="gebouwen")
    return batch.output


def _prepare_heights(
    tiles: list[Path],
    ahn: rasterio.io.DatasetReader,
    path: Path,
    config: DemConfig,
    overwrite: bool,
    workers: int = 1,
) -> None:
    """Assign each ID once; persist batches and retain partial tables on failure.

    The caller checks input/configuration identity before reuse. Only the
    coordinator writes the combined table. Worker count can change on resume.
    Legacy partial tables use the same schema and are reused as well.
    """
    reuse = path.exists() and not overwrite
    temporary = path.with_suffix(".tmp.gpkg")
    recovery = path.with_suffix(".resume.gpkg")
    batch_dir = path.parent / "gebouwhoogten_batches"
    batch_dir.mkdir(exist_ok=True)
    if overwrite:
        temporary.unlink(missing_ok=True)
        recovery.unlink(missing_ok=True)
        for batch_path in batch_dir.glob("*.gpkg"):
            batch_path.unlink()
    elif not reuse and not temporary.exists() and recovery.exists():
        # A live SQLite backup protects progress when stopping legacy code that
        # deletes its temporary table in a finally block.
        replace_file(recovery, temporary)
    target = path if reuse else temporary
    if not reuse:
        for batch_path in sorted(batch_dir.glob("*.gpkg")):
            if batch_path.name.startswith("."):
                continue
            _append_heights(target, wgpd.read_file(batch_path, layer="gebouwen"))
    count = 0
    if target.exists():
        with closing(sqlite3.connect(target)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM gebouwen").fetchone()[0]
        logger.info("Reusing %s stored building elevations from %s", count, target)
    started = monotonic()
    completed = 0
    pending: dict[Future[Path], _HeightBatch] = {}
    workers = min(workers, len(tiles))

    def report(stage: str = "running") -> None:
        elapsed = round(monotonic() - started, 1)
        _save_json(
            path.parent / "gebouwhoogten_status.json",
            {
                "stage": stage,
                "completed_tiles": completed,
                "total_tiles": len(tiles),
                "completed_buildings": count,
                "active_batches": len(pending),
                "workers": workers,
                "elapsed_seconds": elapsed,
            },
        )
        logger.info(
            "Gebouwhoogten: %s/%s tegelbatches gereed; %s gebouwen opgeslagen; "
            "%s batches actief; %s workers; %.1f minuten verstreken",
            completed,
            len(tiles),
            count,
            len(pending),
            workers,
            elapsed / 60,
        )

    def collect() -> None:
        nonlocal count, completed
        ready, _ = wait(pending, timeout=30, return_when=FIRST_COMPLETED)
        for future in ready:
            batch_path = future.result()
            count += _append_heights(
                target, wgpd.read_file(batch_path, layer="gebouwen")
            )
            del pending[future]
            completed += 1
        report()

    pool = (
        ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"))
        if workers > 1 and not reuse
        else nullcontext()
    )
    report()
    with pool as executor:
        for number, tile in enumerate(tiles, 1):
            while len(pending) >= workers:
                collect()
            buildings, selected = _read_buildings(
                [tile], config.building_max_search_distance_m
            )
            cached = _height_rows(target, selected) if target.exists() else None
            known = set(cached.gebouw_id) if cached is not None else set()
            if known:
                _check_height_identity(buildings, cached)
            for batch in pending.values():
                shared = selected & batch.selected_ids
                if shared:
                    _check_height_identity(
                        buildings,
                        batch.buildings[batch.buildings.gebouw_id.isin(shared)],
                    )
                    known.update(shared)
            missing = selected - known
            if reuse and missing:
                raise ValueError("Stored building elevations do not match selected IDs")
            if missing or (not target.exists() and not pending):
                tile_id = _tile_paths(path.parent, tile).terrain.parent.name
                batch = _HeightBatch(
                    buildings,
                    missing,
                    Path(ahn.name),
                    batch_dir / f"{tile_id}.gpkg",
                    config,
                )
                if executor is None:
                    batch_path = _height_batch_worker(batch)
                    count += _append_heights(
                        target, wgpd.read_file(batch_path, layer="gebouwen")
                    )
                    completed += 1
                else:
                    pending[executor.submit(_height_batch_worker, batch)] = batch
            else:
                completed += 1
            if pending or number % 10 == 0 or number == len(tiles):
                report()
        while pending:
            collect()
    if not reuse:
        wgpd.read_file(target, layer="gebouwen", where="1=0")
        replace_file(target, path)
    recovery.unlink(missing_ok=True)
    report("complete")
    logger.info("%s building elevations in %s", "Reusing" if reuse else "Stored", path)


def _tile_heights(tile: Path, height_path: Path) -> pd.DataFrame:
    selected = set()
    with rasterio.open(building_paths(tile)[0]) as ids:
        for _, window in ids.block_windows(1):
            selected.update(
                int(value) for value in np.unique(ids.read(1, window=window)) if value
            )
    return _height_rows(height_path, selected, geometry=False)


def _build_tile_worker(
    arguments: tuple[Path, Path, Path, Path, DemConfig, bool],
) -> DemTilePaths:
    tile, ahn_path, height_path, target_dir, config, overwrite = arguments
    heights = _tile_heights(tile, height_path)
    with (
        tile_logging(_tile_paths(target_dir, tile).terrain.parent / "workflow.log"),
        rasterio.open(ahn_path) as ahn,
    ):
        return _build_tile(tile, ahn, heights, target_dir, config, overwrite)


def bouw_dem_tiles(
    target_dir: Path,
    *,
    ahn_vrt_path: Path,
    landuse_tiles: list[Path],
    config: DemConfig | None = None,
    overwrite: bool = False,
    workers: int | None = None,
    building_workers: int | None = None,
    landgebied_path: Path | None = None,
) -> Path:
    """Produce a DEM on exactly the supplied functional-land-use tile grid.

    Parameters
    ----------
    target_dir : pathlib.Path
        Dedicated output folder. Matching completed tiles/heights are reused.
    ahn_vrt_path : pathlib.Path
        Original AHN-DTM mosaic covering cores and donor halos.
    landuse_tiles : list of pathlib.Path
        Land-use cores with matching bronnen, gebouw_ids and gebouwen companions.
        Complete prepared geometries are used for building sampling; only source
        code 10 determines building output cells. No BAG is read here.
    config : DemConfig, optional
        Buffer/percentile/interpolation settings; no landgebied restriction.
    overwrite : bool, optional
        Rebuild products within the same input/configuration identity. Changed
        inputs or settings require a new output directory.

    workers : int, optional
        Parallel core tiles; defaults to settings.dem_workers. Building heights
        are determined first. Worker count may change on resume.
    building_workers : int, optional
        Parallel building-height batches; defaults to settings.dem_building_workers.
        Completed batches and partial height tables are reused after interruption.
    landgebied_path : pathlib.Path, optional
        GeoPackage with the landgebied boundary for the final coverage check.
        NoData is reported separately outside it, in water cells (100, 228),
        and in other land use. NoData never blocks publication.
        This affects validation only; computed tiles and heights remain reusable.

    Returns
    -------
    pathlib.Path
        ``dem.tif`` COG, accompanied by dem.vrt, dem_bron.vrt/tif, ahn_bron.vrt/tif, nodata.gpkg,
        persistent gebouwhoogten.gpkg and core-only intermediate rasters.
        ``dem_float.tif`` contains decoded Float32 heights in metres.
        Failed building estimates retain the underlying terrain.

    Raises
    ------
    ValueError
        If inputs/configuration changed or grids disagree. Remaining NoData
        is recorded in diagnostics and does not prevent publication.
    """
    config = config or DemConfig()
    workers = resolve_workers(workers, settings.dem_workers)
    building_workers = resolve_workers(building_workers, settings.dem_building_workers)
    target_dir = Path(target_dir)
    if not landuse_tiles or len(
        {_tile_paths(target_dir, path).terrain for path in landuse_tiles}
    ) != len(landuse_tiles):
        raise ValueError("Provide a nonempty list of spatially distinct land-use tiles")
    target_dir.mkdir(parents=True, exist_ok=True)
    inputs = [ahn_vrt_path]
    for tile in landuse_tiles:
        inputs.extend([tile, source_path(tile), *building_paths(tile)])
    identity = {
        "version": VERSION,
        "config": asdict(config),
        "inputs": [_file_identity(path) for path in inputs],
    }
    # JSON normalizes tuple-valued configuration before comparing on resume.
    identity = json.loads(json.dumps(identity))
    manifest = target_dir / "dem_inputs.json"
    if (
        manifest.exists()
        and json.loads(manifest.read_text(encoding="utf-8")) != identity
    ):
        raise ValueError(
            "DEM inputs/configuration changed; choose a new production folder"
        )
    _save_json(manifest, identity)
    if landgebied_path is not None and not Path(landgebied_path).is_file():
        raise FileNotFoundError(landgebied_path)
    coverage_identity = {
        "version": 1,
        "landgebied": _file_identity(Path(landgebied_path))
        if landgebied_path is not None
        else None,
        "water_codes": list(WATER_CODES),
    }
    coverage_manifest = target_dir / "dem_coverage_inputs.json"
    if (
        coverage_manifest.exists()
        and json.loads(coverage_manifest.read_text(encoding="utf-8"))
        != coverage_identity
    ):
        raise ValueError("DEM coverage inputs changed; choose a new production folder")
    _save_json(coverage_manifest, coverage_identity)
    with rasterio.open(ahn_vrt_path) as ahn:
        for tile in landuse_tiles:
            with rasterio.open(tile) as reference:
                _validate_grid(ahn, reference)
        height_path = target_dir / "gebouwhoogten.gpkg"
        _prepare_heights(
            landuse_tiles, ahn, height_path, config, overwrite, building_workers
        )
        worker_count = min(workers, len(landuse_tiles))
        logger.info(
            "Processing %s DEM tiles with %s workers", len(landuse_tiles), worker_count
        )
        if worker_count == 1:
            paths = []
            for tile in landuse_tiles:
                paths.append(
                    _build_tile_worker(
                        (tile, ahn_vrt_path, height_path, target_dir, config, overwrite)
                    )
                )
                logger.info("DEM-tegels: %s/%s gereed", len(paths), len(landuse_tiles))
        else:
            arguments = [
                (tile, ahn_vrt_path, height_path, target_dir, config, overwrite)
                for tile in landuse_tiles
            ]
            with ProcessPoolExecutor(
                max_workers=worker_count, mp_context=get_context("spawn")
            ) as executor:
                futures = {
                    executor.submit(_build_tile_worker, argument): argument[0]
                    for argument in arguments
                }
                completed_paths = {}
                for future in as_completed(futures):
                    result = future.result()
                    completed_paths[futures[future]] = result
                    logger.info(
                        "Completed DEM tile %s (%s/%s)",
                        result.terrain.parent.name,
                        len(completed_paths),
                        len(landuse_tiles),
                    )
                paths = [completed_paths[tile] for tile in landuse_tiles]
        completion = target_dir / "dem_complete.json"
        core_identity = [
            _file_identity(path) for group in paths for path in group.files
        ]
        products = [
            target_dir / name
            for name in (
                "dem.vrt",
                "dem.tif",
                "dem_bron.vrt",
                "dem_bron.tif",
                "ahn_bron.vrt",
                "ahn_bron.tif",
                "nodata.gpkg",
            )
        ]
        float_path = target_dir / "dem_float.tif"
        base_completion = target_dir / "dem_base_complete.json"
        checkpoint = completion if completion.exists() else base_completion
        if not overwrite and checkpoint.exists():
            previous = json.loads(checkpoint.read_text(encoding="utf-8"))
            if (
                previous.get("coverage") == coverage_identity
                and previous.get("diagnostics_version") == DIAGNOSTICS_VERSION
                and previous.get("cores") == core_identity
                and previous.get("products")
                == [_file_identity(path) for path in products]
            ):
                # Export-only upgrades leave existing tiles and integer products intact.
                if (
                    previous.get("float_export") != _file_identity(float_path)
                    or not float_path.is_file()
                ):
                    _save_json(base_completion, previous)
                    completion.unlink(missing_ok=True)
                    create_float_dem(target_dir / "dem.tif", float_path)
                    previous["float_export"] = _file_identity(float_path)
                    _save_json(completion, previous)
                if not completion.exists():
                    _save_json(completion, previous)
                logger.info("Reusing complete DEM mosaics and COGs in %s", target_dir)
                return target_dir / "dem.tif"
        completion.unlink(missing_ok=True)
        base_completion.unlink(missing_ok=True)
        logger.info("DEM: diagnostiek uit %s tegels samenvoegen", len(paths))
        diagnostics = [
            wgpd.read_file(paths_for_tile.diagnostics, layer="nodata")
            for paths_for_tile in paths
        ]
        unresolved = wgpd.read_file(
            height_path, layer="gebouwen", where="hoogte_m IS NULL"
        )
        unresolved["bron"] = "Gebouw"
        unresolved["categorie"] = "Gebouw"
        unresolved["reden"] = (
            "Geen oorspronkelijke AHN-donor binnen maximale gebouwzoekafstand"
        )
        diagnostics = [frame[frame.bron != "Gebouw"] for frame in diagnostics]
        diagnostics.append(unresolved.drop(columns="hoogte_m"))
        merged = gpd.GeoDataFrame(
            pd.concat(diagnostics, ignore_index=True), crs=ahn.crs
        )
        merged["zoekafstand_m"] = pd.to_numeric(merged.zoekafstand_m).astype("float64")
        for column in ("gebouw_id", "donor_aantal"):
            merged[column] = pd.to_numeric(merged[column]).astype("Int64")
        write_geopackage_layer_atomically(
            merged, target_dir / "nodata.gpkg", layer_name="nodata"
        )
    counts = _check_coverage(paths, landuse_tiles, landgebied_path)
    _save_json(target_dir / "dem_coverage.json", asdict(counts))
    logger.info("DEM: VRT's en COG-eindbestanden samenstellen")
    ahn_source_vrt = create_vrt_file(
        target_dir / "ahn_bron.vrt", files=[p.ahn_provenance for p in paths]
    )
    create_cog_file(ahn_source_vrt, target_dir / "ahn_bron.tif", overwrite=True)
    dem_vrt = create_vrt_file(
        target_dir / "dem.vrt",
        files=[p.terrain for p in paths] + [p.buildings for p in paths],
    )
    source_vrt = create_vrt_file(
        target_dir / "dem_bron.vrt", files=[p.provenance for p in paths]
    )
    # Repair changed/incomplete products; matching complete products returned above.
    create_cog_file(source_vrt, target_dir / "dem_bron.tif", overwrite=True)
    result = create_cog_file(
        dem_vrt, target_dir / "dem.tif", overwrite=True, overview_resampling="average"
    )
    _save_json(
        base_completion,
        {
            "coverage": coverage_identity,
            "diagnostics_version": DIAGNOSTICS_VERSION,
            "cores": core_identity,
            "products": [_file_identity(path) for path in products],
        },
    )
    create_float_dem(result, float_path)
    _save_json(
        completion,
        {
            "coverage": coverage_identity,
            "diagnostics_version": DIAGNOSTICS_VERSION,
            "cores": core_identity,
            "float_export": _file_identity(float_path),
            "products": [_file_identity(path) for path in products],
        },
    )
    logger.info("DEM production complete: %s", result)
    return result
