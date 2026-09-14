"""Cached full source raster extents for local AHN mosaics.

Coverage is the union of rectangular TIFF bounds, including all internal
NoData. Source masks and pixel values are never read to determine coverage.
"""

import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.warp import transform_bounds
from shapely.geometry import Polygon, box

from waterlagen.logger import get_logger
from waterlagen.raster.grid import RasterGrid

logger = get_logger(__name__)


def _file_version(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=16)
def _vrt_sources(path: Path, version: tuple[int, int]) -> tuple[Path, ...]:
    """Parse a flat VRT once per file version; no source pixel reads here."""
    root = ET.parse(path).getroot()
    band = root.find("./VRTRasterBand[@band='1']")
    if band is None or root.get("subClass") or band.get("subClass"):
        raise ValueError("Coverage requires a flat SimpleSource/ComplexSource VRT")
    sources = []
    for element in band:
        if not element.tag.endswith("Source"):
            continue
        if element.tag not in {"SimpleSource", "ComplexSource"}:
            raise ValueError(f"Unsupported VRT coverage source: {element.tag}")
        filename = element.find("SourceFilename")
        if filename is None or not filename.text:
            raise ValueError("VRT coverage requires SourceFilename")
        source_path = Path(filename.text)
        if filename.get("relativeToVRT") == "1":
            source_path = path.parent / source_path
        sources.append(source_path.resolve())
    if not sources:
        raise ValueError("VRT has no supported raster sources for coverage")
    return tuple(sources)


@lru_cache(maxsize=256)
def _source_extent(
    path: Path,
    versions: tuple[tuple[int, int], ...],
    crs: str,
) -> Polygon:
    """Read the full raster bounds from metadata, ignoring masks and NoData."""
    logger.info("Reading DEM coverage extent for %s", path.name)
    with rasterio.open(path) as dataset:
        if dataset.driver == "VRT":
            raise ValueError(
                "Nested VRT coverage is not supported; use a flat source mosaic"
            )
        bounds = transform_bounds(dataset.crs, crs, *dataset.bounds)
    return box(*bounds)


def _coverage_mask(source: rasterio.io.DatasetReader, grid: RasterGrid) -> np.ndarray:
    """Union full source raster extents on the exact DEM target grid.

    In-memory caches are invalidated by VRT/source/sidecar mtime and size, and
    target CRS. Extents are rasterized at the requested resolution and alignment.
    No coverage files are written beside input data.
    """
    path = Path(source.name).resolve()
    if source.driver == "VRT":
        sources = _vrt_sources(path, _file_version(path))
    else:
        sources = (path,)
    target = box(*grid.bounds)
    extents = []
    for path in sources:
        versions = [_file_version(path)]
        for suffix in (".msk", ".aux.xml", ".ovr"):
            sidecar = Path(str(path) + suffix)
            versions.append(_file_version(sidecar) if sidecar.exists() else (0, 0))
        extent = _source_extent(path, tuple(versions), str(grid.crs))
        if extent.intersection(target).area:
            extents.append((extent, 1))
    if not extents:
        return np.zeros((grid.height, grid.width), dtype=bool)
    return rasterize(
        extents,
        out_shape=(grid.height, grid.width),
        transform=grid.transform,
        dtype="uint8",
        fill=0,
    ).astype(bool)
