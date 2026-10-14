"""Read, validate and prepare optional height changes independently of targets."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from math import ceil, floor
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from rasterio.features import rasterize
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from shapely import force_2d, union_all
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from waterlagen import _geopandas as wgpd
from waterlagen._crs import format_crs, same_crs
from waterlagen._filesystem import replace_file
from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._production import _file_identity
from waterlagen.logger import get_logger
from waterlagen.raster.grid import RasterGrid
from waterlagen.settings import settings

from .config import BrandlagenConfig, _brand_number

logger = get_logger(__name__)
BRAND_POLICY = "relative_priority_abs_v1"
BRAND_LAYER = "brandlagen"
SOURCE_COLUMNS = ["bronbestand", "bronlaag", "bron_fid"]


@dataclass(frozen=True)
class _PreparedBrandlagen:
    """Small worker input referencing validated data; never carries geometries."""

    path: Path
    signature: str


def _digest(values: object) -> str:
    return sha256(
        json.dumps(values, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def _brand_identity(config: BrandlagenConfig | None) -> dict:
    """Track configured sources, SQLite edits, defaults and the burn policy."""
    config = config or BrandlagenConfig()
    return {
        "policy": BRAND_POLICY,
        "crs": format_crs(settings.crs),
        "brandwaarde": config.brandwaarde,
        "prioriteit": config.prioriteit,
        "lagen": [
            {
                "source": _file_identity(layer.path),
                "wal": _file_identity(Path(str(layer.path) + "-wal")),
                "layer": layer.layer,
                "brandwaarde": layer.brandwaarde,
                "prioriteit": layer.prioriteit,
            }
            for layer in config.lagen
        ],
    }


def _empty_brandlagen() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "brandwaarde": pd.Series(dtype="float64"),
            "prioriteit": pd.Series(dtype="int64"),
            "bronbestand": pd.Series(dtype="str"),
            "bronlaag": pd.Series(dtype="str"),
            "bron_fid": pd.Series(dtype="int64"),
        },
        geometry=[],
        crs=settings.crs,
    )


def _sort_brandlagen(features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return (
        features.assign(_absolute=features.brandwaarde.abs())
        .sort_values(["prioriteit", "_absolute", *SOURCE_COLUMNS], kind="stable")
        .drop(columns="_absolute")
        .reset_index(drop=True)
    )


def _read_brandlagen(
    config: BrandlagenConfig, spatial_selection: BaseGeometry | None
) -> tuple[gpd.GeoDataFrame, list[str]]:
    records = []
    errors = []
    if spatial_selection is not None and spatial_selection.is_empty:
        return _empty_brandlagen(), errors
    for source in config.lagen:
        label = f"{source.path} / {source.layer}"
        try:
            info = pyogrio.read_info(source.path, layer=source.layer)
            if info["crs"] is None:
                raise ValueError("layer has no CRS")
            fields = [
                name for name in ("brandwaarde", "prioriteit") if name in info["fields"]
            ]
            options = {"layer": source.layer, "fid_as_index": True, "columns": fields}
            if spatial_selection is not None:
                selection = gpd.GeoSeries([spatial_selection], crs=settings.crs)
                options["bbox"] = tuple(selection.to_crs(info["crs"]).total_bounds)
            logger.info("Reading brandlaag %s", label)
            features = wgpd.read_file(source.path, **options)
            if not same_crs(features.crs, settings.crs):
                features = features.to_crs(settings.crs)
        except (OSError, ValueError, RuntimeError) as error:
            errors.append(f"{label}: {error}")
            continue
        for fid, row in features.iterrows():
            location = f"{label} / FID {fid}"
            geometry = row.geometry
            if geometry is None or geometry.is_empty or not geometry.is_valid:
                errors.append(f"{location}: missing, empty or invalid geometry")
                continue
            if geometry.geom_type not in {
                "LineString",
                "MultiLineString",
                "Polygon",
                "MultiPolygon",
            }:
                errors.append(f"{location}: unsupported geometry {geometry.geom_type}")
                continue
            if spatial_selection is not None and not geometry.intersects(
                spatial_selection
            ):
                continue
            values = {}
            for name in ("brandwaarde", "prioriteit"):
                value = row.get(name)
                if pd.isna(value):
                    value = getattr(source, name)
                if value is None:
                    value = getattr(config, name)
                try:
                    values[name] = _brand_number(value, priority=name == "prioriteit")
                except ValueError as error:
                    errors.append(
                        f"{location}: {name}: {error}; no valid value/default"
                    )
            if len(values) == 2:
                records.append(
                    {
                        **values,
                        "bronbestand": str(source.path),
                        "bronlaag": source.layer,
                        "bron_fid": int(fid),
                        "geometry": force_2d(geometry),
                    }
                )
    if not records:
        return _empty_brandlagen(), errors
    return _sort_brandlagen(gpd.GeoDataFrame(records, crs=settings.crs)), errors


def _raise_brand_errors(errors: list[str]) -> None:
    if errors:
        raise ValueError("Invalid brandlagen:\n" + "\n".join(sorted(set(errors))))


def read_brandlagen(
    config: BrandlagenConfig, *, spatial_selection: BaseGeometry | None = None
) -> gpd.GeoDataFrame:
    """Combine GeoPackage layers into ordered optional burn objects.

    Parameters
    ----------
    config : BrandlagenConfig
        Sources and fallback values. Object values override layer and global
        defaults. Numeric zero is preserved; missing columns and NULL fall back.
    spatial_selection : shapely.geometry.base.BaseGeometry, optional
        Selection in the configured project CRS, including any required buffers.
        Geometries are selected without clipping or adding a line buffer.

    Returns
    -------
    geopandas.GeoDataFrame
        Project-CRS 2D geometries, signed metre ``brandwaarde``, integer
        ``prioriteit`` and ``bronbestand``, ``bronlaag``, ``bron_fid`` provenance.
        Sorted by increasing priority and absolute value for replacement burning.

    Raises
    ------
    ValueError
        Collected source, geometry or attribute errors with source/FID details.

    Notes
    -----
    Reading does not check pixel conflicts: raster and tile preparation do that
    once on the actual calculation grids, before reading elevation pixels.
    """
    features, errors = _read_brandlagen(config, spatial_selection)
    _raise_brand_errors(errors)
    return features


def _conflict_window(features: gpd.GeoDataFrame, grid: RasterGrid) -> Window:
    """Bound all candidate geometries, with a cell margin for boundary lines."""
    minx, miny, maxx, maxy = features.total_bounds
    left, top = (~grid.transform) * (minx, maxy)
    right, bottom = (~grid.transform) * (maxx, miny)
    col = max(0, floor(left) - 1)
    row = max(0, floor(top) - 1)
    stop_col = min(grid.width, ceil(right) + 1)
    stop_row = min(grid.height, ceil(bottom) + 1)
    return Window(col, row, stop_col - col, stop_row - row)


def _conflict_errors(
    features: gpd.GeoDataFrame, grids: Sequence[RasterGrid]
) -> list[str]:
    """Report every involved object, including objects hidden by later burns."""
    conflicts = set()
    for grid in grids:
        positions = features.sindex.query(box(*grid.bounds), predicate="intersects")
        selected = features.iloc[positions]
        for priority, group in selected.groupby("prioriteit", sort=False):
            positive = group[group.brandwaarde > 0]
            negative = group[group.brandwaarde < 0]
            if positive.empty or negative.empty:
                continue
            window = _conflict_window(group, grid)
            if window.width <= 0 or window.height <= 0:
                continue
            options = {
                "out_shape": (int(window.height), int(window.width)),
                "transform": window_transform(window, grid.transform),
                "dtype": "uint8",
                "all_touched": False,
            }
            positive_mask = rasterize([(g, 1) for g in positive.geometry], **options)
            negative_mask = rasterize([(g, 1) for g in negative.geometry], **options)
            overlap = (positive_mask != 0) & (negative_mask != 0)
            if not overlap.any():
                continue
            for row in group.itertuples():
                if row.brandwaarde == 0:
                    continue
                mask = rasterize([(row.geometry, 1)], **options)
                if np.any(overlap & (mask != 0)):
                    conflicts.add(
                        f"{row.bronbestand} / {row.bronlaag} / FID {row.bron_fid}: "
                        f"opposite signs share a raster cell at prioriteit {priority}"
                    )
    return sorted(conflicts)


def _prepare_brandlagen(
    config: BrandlagenConfig | None, grids: Sequence[RasterGrid], path: Path
) -> _PreparedBrandlagen | None:
    """Validate once, persist a local selection, and reuse an unchanged snapshot."""
    if config is None or not config.lagen or not grids:
        return None
    if any(source.path == path.resolve() for source in config.lagen):
        raise ValueError(
            "Prepared brandlagen output must not replace an input GeoPackage"
        )
    signature = _digest(
        {
            "inputs": _brand_identity(config),
            "grids": [
                (grid.bounds, grid.resolution, format_crs(grid.crs)) for grid in grids
            ],
        }
    )
    manifest = path.with_suffix(".json")
    if manifest.is_file() and path.is_file():
        try:
            previous = json.loads(manifest.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            previous = {}
        if previous == {"signature": signature, "snapshot": _file_identity(path)}:
            logger.info("Reusing validated brandlagen %s", path)
            return _PreparedBrandlagen(path, signature)
    logger.info("Validating brandlagen for %s calculation grids", len(grids))
    selection = union_all([box(*grid.bounds) for grid in grids])
    features, errors = _read_brandlagen(config, selection)
    errors.extend(_conflict_errors(features, grids))
    _raise_brand_errors(errors)
    if signature != _digest(
        {
            "inputs": _brand_identity(config),
            "grids": [
                (grid.bounds, grid.resolution, format_crs(grid.crs)) for grid in grids
            ],
        }
    ):
        raise ValueError(
            "Brandlagen changed during validation; retry with stable sources"
        )
    write_geopackage_layer_atomically(features, path, layer_name=BRAND_LAYER)
    temporary = manifest.with_suffix(".tmp.json")
    temporary.write_text(
        json.dumps(
            {
                "signature": signature,
                "snapshot": _file_identity(path),
            }
        ),
        encoding="utf-8",
    )
    replace_file(temporary, manifest)
    logger.info("Prepared %s brandobjects in %s", len(features), path)
    return _PreparedBrandlagen(path, signature)


def _optional_burn_values(
    prepared: _PreparedBrandlagen | None, grid: RasterGrid
) -> np.ndarray:
    if prepared is None:
        return np.zeros((grid.height, grid.width), dtype="float64")
    features = wgpd.read_file(prepared.path, layer=BRAND_LAYER, bbox=grid.bounds)
    if features.empty:
        return np.zeros((grid.height, grid.width), dtype="float64")
    features = _sort_brandlagen(features)
    logger.info(
        "Rasterizing %s optional brandobjects from %s", len(features), prepared.path
    )
    return rasterize(
        list(zip(features.geometry, features.brandwaarde)),
        out_shape=(grid.height, grid.width),
        transform=grid.transform,
        dtype="float64",
        fill=0,
        all_touched=False,
    )


def _burn_signature(
    watersysteem_path: Path, burn_depth_m: float, prepared: _PreparedBrandlagen | None
) -> str:
    return _digest(
        {
            "policy": BRAND_POLICY,
            "watersysteem": _file_identity(watersysteem_path),
            "burn_depth_m": burn_depth_m,
            "optional": prepared.signature if prepared is not None else None,
        }
    )
