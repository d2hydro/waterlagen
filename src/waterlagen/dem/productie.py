"""Core-only DEM tiles, reusable building heights and ordered VRT/COG assembly."""

import json
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
from dataclasses import asdict
from math import ceil
from multiprocessing import get_context
from pathlib import Path
from uuid import uuid4

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.features import shapes
from rasterio.windows import Window
from shapely.geometry import shape

from waterlagen import _geopandas as wgpd
from waterlagen._crs import same_crs
from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._production import _file_identity
from waterlagen.ahn import interpolate
from waterlagen.areas import resolve_workers
from waterlagen.functioneel_landgebruik.gebouwen import (
    building_paths,
    validate_buildings,
)
from waterlagen.logger import get_logger
from waterlagen.raster.overviews import build_raster_overviews
from waterlagen.raster.vrt import create_cog_file, create_vrt_file
from waterlagen.settings import settings

from .config import DemConfig
from .gebouwen import aligned_window, calculate_building_elevations

logger = get_logger(__name__)
VERSION = "1"


def _save_json(path: Path, content: dict) -> None:
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(
        json.dumps(content, sort_keys=True, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


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
        temporary.replace(path)
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


def _tile_paths(output: Path, name: str) -> tuple[Path, Path, Path, Path]:
    return (
        output / "tiles" / "ahn_filled" / name,
        output / "tiles" / "gebouwen" / name,
        output / "tiles" / "dem_bron" / name,
        output / "tiles" / "nodata" / Path(name).with_suffix(".gpkg"),
    )


def _reuse_tile(
    paths: tuple[Path, Path, Path, Path],
    marker: Path,
    reference: rasterio.io.DatasetReader,
) -> bool:
    if not marker.is_file() or not all(path.is_file() for path in paths):
        return False
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    for path in paths[:3]:
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


def _build_tile(
    tile: Path,
    ahn: rasterio.io.DatasetReader,
    heights: pd.DataFrame,
    output: Path,
    config: DemConfig,
    overwrite: bool,
) -> tuple[Path, Path, Path, Path]:
    paths = _tile_paths(output, tile.name)
    marker = output / "tiles" / "status" / tile.with_suffix(".json").name
    marker.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(tile) as reference:
        _validate_grid(ahn, reference)
        if not overwrite and _reuse_tile(paths, marker, reference):
            logger.info("Reusing DEM tile %s", tile.name)
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
        provenance[building] = np.where(resolved[inverse], 2, 0)
        # A NoData building overlay otherwise falls through to the underlying
        # terrain in GDAL VRT mosaics. Clear terrain at unresolved buildings.
        unresolved = building & (provenance == 0)
        terrain[unresolved] = _nodata(ahn)
        records = []
        missing_ahn = (provenance == 0) & ~building
        for geometry, _ in shapes(
            missing_ahn.astype("uint8"), mask=missing_ahn, transform=reference.transform
        ):
            records.append(
                {
                    "bron": "AHN",
                    "reden": "Geen geldige AHN-hoogte binnen interpolatieafstand",
                    "identificatie": None,
                    "gebouw_id": None,
                    "zoekafstand_m": config.interpolation_max_distance_m,
                    "donor_aantal": 0,
                    "geometry": shape(geometry),
                }
            )
        diagnostics = _diagnostics(records, reference.crs)
        pair = uuid4().hex
        _write_tile(paths[0], terrain, ahn, reference.transform, config, pair)
        _write_tile(paths[1], building_values, ahn, reference.transform, config, pair)
        _write_tile(
            paths[2],
            provenance,
            ahn,
            reference.transform,
            config,
            pair,
            provenance=True,
        )
        write_geopackage_layer_atomically(diagnostics, paths[3], layer_name="nodata")
        _save_json(marker, {"output_pair": pair})
        logger.info(
            "DEM tile %s: %s original, %s interpolated, %s building, %s unresolved",
            tile.name,
            int((provenance == 1).sum()),
            int((provenance == 3).sum()),
            int((provenance == 2).sum()),
            int((provenance == 0).sum()),
        )
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


def _prepare_heights(
    tiles: list[Path],
    ahn: rasterio.io.DatasetReader,
    path: Path,
    config: DemConfig,
    overwrite: bool,
) -> None:
    """Sample complete footprints in tile-sized batches into one atomic table."""
    reuse = path.exists() and not overwrite
    temporary = path.with_suffix(".tmp.gpkg")
    if not reuse:
        temporary.unlink(missing_ok=True)
    target = path if reuse else temporary
    try:
        for tile in tiles:
            buildings, selected = _read_buildings(
                [tile], config.building_max_search_distance_m
            )
            cached = _height_rows(target, selected) if target.exists() else None
            known = set(cached.gebouw_id) if cached is not None else set()
            if known:
                expected = buildings.set_index("gebouw_id").loc[cached.gebouw_id]
                if (
                    expected.identificatie.astype(str).tolist()
                    != cached.identificatie.astype(str).tolist()
                    or expected.geometry.to_wkb().tolist()
                    != cached.geometry.to_wkb().tolist()
                ):
                    raise ValueError(
                        "Building identity/complete geometry differs between tiles"
                    )
            missing = selected - known
            if reuse and missing:
                raise ValueError("Stored building elevations do not match selected IDs")
            if missing or not target.exists():
                heights = calculate_building_elevations(buildings, missing, ahn, config)
                heights.to_file(
                    target,
                    layer="gebouwen",
                    driver="GPKG",
                    mode="a" if target.exists() else "w",
                )
                with closing(sqlite3.connect(target)) as connection:
                    connection.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS gebouw_id_lookup ON gebouwen (gebouw_id)"
                    )
                    connection.commit()
        if not reuse:
            # Read the final schema before publishing the complete table.
            wgpd.read_file(target, layer="gebouwen", where="1=0")
            target.replace(path)
        logger.info(
            "%s building elevations in %s", "Reusing" if reuse else "Stored", path
        )
    finally:
        if not reuse:
            temporary.unlink(missing_ok=True)


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
) -> tuple[Path, Path, Path, Path]:
    tile, ahn_path, height_path, target_dir, config, overwrite = arguments
    heights = _tile_heights(tile, height_path)
    with rasterio.open(ahn_path) as ahn:
        return _build_tile(tile, ahn, heights, target_dir, config, overwrite)


def bouw_dem_tiles(
    target_dir: Path,
    *,
    ahn_vrt_path: Path,
    landuse_tiles: list[Path],
    config: DemConfig | None = None,
    overwrite: bool = False,
    workers: int | None = None,
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

    Returns
    -------
    pathlib.Path
        ``dem.tif`` COG, accompanied by dem.vrt, dem_bron.vrt/tif, nodata.gpkg,
        persistent gebouwhoogten.gpkg and core-only intermediate rasters.
    """
    config = config or DemConfig()
    workers = resolve_workers(workers, settings.dem_workers)
    target_dir = Path(target_dir)
    if not landuse_tiles or len({path.name for path in landuse_tiles}) != len(
        landuse_tiles
    ):
        raise ValueError("Provide a nonempty list of uniquely named land-use tiles")
    target_dir.mkdir(parents=True, exist_ok=True)
    inputs = [ahn_vrt_path]
    for tile in landuse_tiles:
        inputs.extend(
            [tile, tile.parent / "bronnen" / tile.name, *building_paths(tile)]
        )
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
    with rasterio.open(ahn_vrt_path) as ahn:
        for tile in landuse_tiles:
            with rasterio.open(tile) as reference:
                _validate_grid(ahn, reference)
        height_path = target_dir / "gebouwhoogten.gpkg"
        _prepare_heights(landuse_tiles, ahn, height_path, config, overwrite)
        worker_count = min(workers, len(landuse_tiles))
        logger.info(
            "Processing %s DEM tiles with %s workers", len(landuse_tiles), worker_count
        )
        if worker_count == 1:
            paths = [
                _build_tile(
                    tile,
                    ahn,
                    _tile_heights(tile, height_path),
                    target_dir,
                    config,
                    overwrite,
                )
                for tile in landuse_tiles
            ]
        else:
            arguments = [
                (tile, ahn_vrt_path, height_path, target_dir, config, overwrite)
                for tile in landuse_tiles
            ]
            with ProcessPoolExecutor(
                max_workers=worker_count, mp_context=get_context("spawn")
            ) as executor:
                paths = []
                for tile, result in zip(
                    landuse_tiles,
                    executor.map(_build_tile_worker, arguments),
                    strict=True,
                ):
                    paths.append(result)
                    logger.info(
                        "Completed DEM tile %s (%s/%s)",
                        tile.name,
                        len(paths),
                        len(landuse_tiles),
                    )
        completion = target_dir / "dem_complete.json"
        core_identity = [_file_identity(path) for group in paths for path in group]
        products = [
            target_dir / name
            for name in (
                "dem.vrt",
                "dem.tif",
                "dem_bron.vrt",
                "dem_bron.tif",
                "nodata.gpkg",
            )
        ]
        if not overwrite and completion.exists():
            previous = json.loads(completion.read_text(encoding="utf-8"))
            if previous.get("cores") == core_identity and previous.get("products") == [
                _file_identity(path) for path in products
            ]:
                logger.info("Reusing complete DEM mosaics and COGs in %s", target_dir)
                return target_dir / "dem.tif"
        completion.unlink(missing_ok=True)
        diagnostics = [
            wgpd.read_file(paths_for_tile[3], layer="nodata")
            for paths_for_tile in paths
        ]
        unresolved = wgpd.read_file(
            height_path, layer="gebouwen", where="hoogte_m IS NULL"
        )
        unresolved["bron"] = "Gebouw"
        unresolved["reden"] = (
            "Geen oorspronkelijke AHN-donor binnen maximale gebouwzoekafstand"
        )
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
    dem_vrt = create_vrt_file(
        target_dir / "dem.vrt", files=[p[0] for p in paths] + [p[1] for p in paths]
    )
    source_vrt = create_vrt_file(
        target_dir / "dem_bron.vrt", files=[p[2] for p in paths]
    )
    # Repair changed/incomplete products; matching complete products returned above.
    create_cog_file(source_vrt, target_dir / "dem_bron.tif", overwrite=True)
    result = create_cog_file(
        dem_vrt, target_dir / "dem.tif", overwrite=True, overview_resampling="average"
    )
    _save_json(
        completion,
        {
            "cores": core_identity,
            "products": [_file_identity(path) for path in products],
        },
    )
    logger.info("DEM production complete: %s", result)
    return result
