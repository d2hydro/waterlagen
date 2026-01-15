from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import geopandas as gpd
from shapely.geometry import Polygon, base
from shapely.ops import unary_union

import rasterio
from rasterio.enums import Resampling
from rasterio.fill import fillnodata
from rasterio.io import MemoryFile
from rasterio.mask import mask as rio_mask
from rasterio.transform import Affine
from rasterio.windows import Window
from rasterio.windows import from_bounds as window_from_bounds
from rasterio.warp import reproject


@dataclass(frozen=True)
class NeighborSides:
    """Simple container describing which sides have a neighboring polygon."""
    left: bool
    right: bool
    top: bool
    bottom: bool


def detect_neighbor_sides(
    tiles_gdf: gpd.GeoDataFrame,
    tile_index: int,
    *,
    tol: float = 1e-9,
) -> NeighborSides:
    """
    Determine which sides of a tile polygon have neighbors that touch it.

    This function is intended for quickly deciding on which sides it makes sense
    to expand a read-window into adjacent tiles.

    Parameters
    ----------
    tiles_gdf : geopandas.GeoDataFrame
        GeoDataFrame containing tile polygons. Must have a geometry column.
    tile_index : int
        Index (row label) of the tile in `tiles_gdf` for which neighbors are detected.
    tol : float, optional
        Tolerance for comparing bounds coordinates. Used to robustly decide whether
        a touching polygon is on the left/right/top/bottom, by default 1e-9.

    Returns
    -------
    NeighborSides
        Booleans for left/right/top/bottom.

    Notes
    -----
    - Uses a spatial index (if available) for efficient neighbor discovery.
    - A neighbor is considered "touching" if geometries touch or overlap slightly
      (depending on how clean the tiling is). This function uses a bbox query and
      then refines with `touches`/`intersects` checks.
    """
    geom = tiles_gdf.loc[tile_index].geometry
    if geom is None or geom.is_empty:
        return NeighborSides(False, False, False, False)

    minx, miny, maxx, maxy = geom.bounds

    # Candidate neighbors via spatial index bbox query
    sidx = tiles_gdf.sindex
    candidate_ilocs = list(sidx.intersection((minx, miny, maxx, maxy)))
    candidates = tiles_gdf.iloc[candidate_ilocs]

    left = right = top = bottom = False
    for idx, row in candidates.iterrows():
        if idx == tile_index:
            continue
        ng = row.geometry
        if ng is None or ng.is_empty:
            continue

        # Refine: only consider real contacts.
        if not (geom.touches(ng) or geom.intersects(ng)):
            continue

        nminx, nminy, nmaxx, nmaxy = ng.bounds

        # Decide "side" by comparing bounds alignment.
        if abs(nmaxx - minx) <= tol:
            left = True
        if abs(nminx - maxx) <= tol:
            right = True
        if abs(nminy - maxy) <= tol:
            top = True
        if abs(nmaxy - miny) <= tol:
            bottom = True

        # Early exit if all sides are found.
        if left and right and top and bottom:
            break

    return NeighborSides(left=left, right=right, top=top, bottom=bottom)


def build_context_geometry(
    tiles_gdf: gpd.GeoDataFrame,
    tile_index: int,
    *,
    include_touching_neighbors: bool = True,
    base_buffer: float = 0.0,
) -> base.BaseGeometry:
    """
    Build a "context" geometry used to define the read-window around a tile.

    The context geometry can optionally include touching neighbor tiles. This helps
    ensure that the interpolation sees valid data just outside the tile boundaries.

    Parameters
    ----------
    tiles_gdf : geopandas.GeoDataFrame
        Tile polygons.
    tile_index : int
        Index of the tile in `tiles_gdf`.
    include_touching_neighbors : bool, optional
        If True, union the tile with touching neighbors before buffering, by default True.
    base_buffer : float, optional
        Buffer (in CRS units) applied to the resulting union geometry. This is applied
        after unioning with neighbors. Use this to guarantee at least some margin, by default 0.0.

    Returns
    -------
    shapely.geometry.base.BaseGeometry
        Context geometry (tile union neighbors and optional buffer).

    Notes
    -----
    - If you want strictly "one cell outside" behavior, use `compute_read_window()`
      with `pad_cells` instead of buffering here. This function focuses on geometry
      unioning; window padding is handled later.
    """
    geom = tiles_gdf.loc[tile_index].geometry
    if geom is None or geom.is_empty:
        return geom

    if not include_touching_neighbors:
        return geom.buffer(base_buffer) if base_buffer else geom

    sidx = tiles_gdf.sindex
    minx, miny, maxx, maxy = geom.bounds
    candidate_ilocs = list(sidx.intersection((minx, miny, maxx, maxy)))
    candidates = tiles_gdf.iloc[candidate_ilocs]

    to_union: List[base.BaseGeometry] = [geom]
    for idx, row in candidates.iterrows():
        if idx == tile_index:
            continue
        ng = row.geometry
        if ng is None or ng.is_empty:
            continue
        if geom.touches(ng):
            to_union.append(ng)

    unioned = unary_union(to_union)
    return unioned.buffer(base_buffer) if base_buffer else unioned


def compute_read_window(
    src: rasterio.io.DatasetReader,
    context_geom: base.BaseGeometry,
    *,
    pad_cells: int = 1,
) -> Tuple[Window, Tuple[float, float, float, float]]:
    """
    Compute a rasterio Window around a context geometry, padded by a number of cells.

    Parameters
    ----------
    src : rasterio.io.DatasetReader
        Open raster source (e.g., VRT).
    context_geom : shapely.geometry.base.BaseGeometry
        Geometry defining the area of interest (often tile union neighbors).
    pad_cells : int, optional
        Number of pixels to pad on each side of the geometry bounds. Use at least 1
        to ensure the closest valid cell outside the tile can be included, by default 1.

    Returns
    -------
    window : rasterio.windows.Window
        Window to read from `src`.
    padded_bounds : tuple of float
        The padded bounds used for the window: (minx, miny, maxx, maxy).

    Notes
    -----
    - The padding uses the source resolution (src.res).
    - The returned window is clipped to the raster extent.
    """
    if context_geom is None or context_geom.is_empty:
        raise ValueError("context_geom is empty; cannot compute read window.")

    minx, miny, maxx, maxy = context_geom.bounds
    xres, yres = src.res
    xpad = pad_cells * abs(xres)
    ypad = pad_cells * abs(yres)

    pb = (minx - xpad, miny - ypad, maxx + xpad, maxy + ypad)

    # Build window from bounds and clip to dataset extent.
    win = window_from_bounds(*pb, transform=src.transform)
    win = win.round_offsets().round_lengths()
    win = win.intersection(Window(0, 0, src.width, src.height))

    return win, pb


def read_resample_and_interpolate(
    src: rasterio.io.DatasetReader,
    window: Window,
    *,
    band: int = 1,
    target_cell_size: Optional[float] = None,
    resampling: Resampling = Resampling.bilinear,
    max_search_distance: int = 250,
) -> Tuple[np.ndarray, Affine, Dict]:
    """
    Read a window from the source raster, optionally resample, and fill nodata via IDW-like interpolation.

    Parameters
    ----------
    src : rasterio.io.DatasetReader
        Open raster source (e.g., VRT).
    window : rasterio.windows.Window
        Window to read.
    band : int, optional
        Band index to read, by default 1.
    target_cell_size : float, optional
        Target pixel size in CRS units. If None, keep original resolution, by default None.
    resampling : rasterio.enums.Resampling, optional
        Resampling method used if `target_cell_size` is provided, by default Resampling.bilinear.
    max_search_distance : int, optional
        Maximum search distance (in pixels of the *output* array) for interpolation, by default 250.

    Returns
    -------
    data_filled : numpy.ndarray
        Filled array (2D) for the read window (and optional resampling).
    out_transform : affine.Affine
        Transform for the returned array.
    out_profile : dict
        Raster profile suitable for writing the returned array.

    Notes
    -----
    - `rasterio.fill.fillnodata` wraps GDAL's fillnodata algorithm, which performs
      an inverse-distance style interpolation from nearby valid pixels.
    - The read uses `boundless=True` to safely include padding near edges. Areas outside
      the dataset become nodata.
    """
    nodata = src.nodata
    if nodata is None:
        raise ValueError("Source raster has nodata=None; set nodata on the VRT or handle masking explicitly.")

    # Read the window as a masked array.
    data = src.read(band, window=window, boundless=True, masked=True)
    win_transform = rasterio.windows.transform(window, src.transform)

    # Convert to a regular ndarray with nodata fill for fillnodata.
    data_arr = np.asarray(data.filled(nodata), dtype=src.dtypes[band - 1])

    out_transform = win_transform
    out_arr = data_arr
    out_nodata = nodata

    if target_cell_size is not None:
        # Compute output shape from requested cell size.
        xres_in, yres_in = src.res
        scale_x = abs(xres_in) / float(target_cell_size)
        scale_y = abs(yres_in) / float(target_cell_size)

        out_height = max(1, int(round(out_arr.shape[0] * scale_y)))
        out_width = max(1, int(round(out_arr.shape[1] * scale_x)))

        # Build output transform by scaling pixel sizes.
        out_transform = out_transform * out_transform.scale(
            (out_arr.shape[1] / out_width),
            (out_arr.shape[0] / out_height),
        )

        dst = np.full((out_height, out_width), out_nodata, dtype=out_arr.dtype)

        # Reproject within same CRS; this effectively resamples.
        reproject(
            source=out_arr,
            destination=dst,
            src_transform=win_transform,
            src_crs=src.crs,
            dst_transform=out_transform,
            dst_crs=src.crs,
            resampling=resampling,
            src_nodata=out_nodata,
            dst_nodata=out_nodata,
        )
        out_arr = dst

    # Mask of valid pixels for interpolation.
    valid_mask = out_arr != out_nodata

    # Fill nodata in-place.
    fillnodata(
        out_arr,
        mask=valid_mask,
        max_search_distance=max_search_distance,
    )

    out_profile = src.profile.copy()
    out_profile.update(
        {
            "driver": "GTiff",
            "height": out_arr.shape[0],
            "width": out_arr.shape[1],
            "count": 1,
            "transform": out_transform,
            "nodata": out_nodata,
        }
    )

    return out_arr, out_transform, out_profile


def clip_to_tile_and_write(
    tile_geom: base.BaseGeometry,
    data: np.ndarray,
    transform: Affine,
    profile: Dict,
    out_path: Path,
    *,
    compress: str = "deflate",
    tiled: bool = True,
    blockxsize: int = 512,
    blockysize: int = 512,
) -> None:
    """
    Clip an interpolated window array to the tile polygon and write it as a GeoTIFF.

    Parameters
    ----------
    tile_geom : shapely.geometry.base.BaseGeometry
        Tile polygon used for clipping.
    data : numpy.ndarray
        2D array representing the interpolated raster for a larger context window.
    transform : affine.Affine
        Transform for `data`.
    profile : dict
        Base raster profile. Must contain at least `crs`, `dtype`, and `nodata`.
    out_path : pathlib.Path
        Output GeoTIFF path.
    compress : str, optional
        Compression for GeoTIFF, by default "deflate".
    tiled : bool, optional
        Write tiled GeoTIFF, by default True.
    blockxsize : int, optional
        Tile width for GTiff tiling, by default 512.
    blockysize : int, optional
        Tile height for GTiff tiling, by default 512.

    Returns
    -------
    None

    Notes
    -----
    - Uses an in-memory dataset to apply `rasterio.mask.mask`.
    - The output is cropped to the polygon bounds and masked outside the polygon.
    """
    if tile_geom is None or tile_geom.is_empty:
        raise ValueError("tile_geom is empty; cannot clip/write.")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    mem_profile = profile.copy()
    mem_profile.update(
        {
            "driver": "GTiff",
            "count": 1,
            "height": data.shape[0],
            "width": data.shape[1],
            "transform": transform,
        }
    )

    # Create an in-memory raster for masking.
    with MemoryFile() as memfile:
        with memfile.open(**mem_profile) as tmp:
            tmp.write(data, 1)

            clipped, clipped_transform = rio_mask(
                tmp,
                [tile_geom],
                crop=True,
                filled=True,
                nodata=mem_profile["nodata"],
            )

    # Prepare output profile.
    out_profile = mem_profile.copy()
    out_profile.update(
        {
            "height": clipped.shape[1],
            "width": clipped.shape[2],
            "transform": clipped_transform,
            "compress": compress,
            "tiled": tiled,
        }
    )
    if tiled:
        out_profile.update({"blockxsize": blockxsize, "blockysize": blockysize})

    with rasterio.open(out_path, "w", **out_profile) as dst:
        dst.write(clipped[0], 1)


def interpolate_tiles_from_vrt(
    vrt_path: Path,
    tiles_gdf: gpd.GeoDataFrame,
    out_dir: Path,
    *,
    id_col: str = "tile_id",
    band: int = 1,
    target_cell_size: Optional[float] = None,
    resampling: Resampling = Resampling.bilinear,
    pad_cells: int = 1,
    max_search_distance: int = 250,
    include_touching_neighbors: bool = True,
) -> gpd.GeoDataFrame:
    """
    Run the full per-tile workflow: detect context, read window, interpolate, clip, and write GeoTIFFs.

    Parameters
    ----------
    vrt_path : pathlib.Path
        Path to the VRT containing multiple DEM tiles.
    tiles_gdf : geopandas.GeoDataFrame
        Tile polygons describing the source tiles. Must contain geometries in the same CRS as the VRT.
    out_dir : pathlib.Path
        Output directory where per-tile GeoTIFFs will be written.
    id_col : str, optional
        Column name used to name output files, by default "tile_id".
    band : int, optional
        Band to read from the VRT, by default 1.
    target_cell_size : float, optional
        If provided, resample to this cell size before interpolation, by default None.
    resampling : rasterio.enums.Resampling, optional
        Resampling method for the optional resample step, by default Resampling.bilinear.
    pad_cells : int, optional
        Window padding in pixels (at least 1 recommended), by default 1.
    max_search_distance : int, optional
        Maximum search distance (pixels) for fillnodata, by default 250.
    include_touching_neighbors : bool, optional
        If True, union tile with touching neighbors before building window, by default True.

    Returns
    -------
    geopandas.GeoDataFrame
        A copy of `tiles_gdf` with two added columns:
        - `out_path`: written file path
        - `neighbor_sides`: detected neighbor sides (as a dict)

    Notes
    -----
    - The "closest cell with data next to the tile" requirement is addressed by:
      (a) unioning with touching neighbors (optional) and
      (b) padding the read window by `pad_cells` so at least one ring of pixels outside the tile
          is included in the interpolation input.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    result = tiles_gdf.copy()
    result["out_path"] = None
    result["neighbor_sides"] = None

    with rasterio.open(vrt_path) as src:
        # Basic CRS safety check.
        if result.crs is not None and src.crs is not None and result.crs != src.crs:
            raise ValueError(f"CRS mismatch: tiles_gdf.crs={result.crs} vs raster.crs={src.crs}")

        for idx, row in result.iterrows():
            tile_id = row.get(id_col, idx)
            tile_geom = row.geometry
            if tile_geom is None or tile_geom.is_empty:
                continue

            # Step 1: detect neighbor sides (useful for diagnostics/logging).
            sides = detect_neighbor_sides(result, idx)
            result.at[idx, "neighbor_sides"] = {
                "left": sides.left,
                "right": sides.right,
                "top": sides.top,
                "bottom": sides.bottom,
            }

            # Step 2: build context geometry and compute a window around it.
            context_geom = build_context_geometry(
                result,
                idx,
                include_touching_neighbors=include_touching_neighbors,
                base_buffer=0.0,
            )
            window, _ = compute_read_window(src, context_geom, pad_cells=pad_cells)

            # Step 3: read + (optional) resample + interpolate nodata.
            filled, out_transform, out_profile = read_resample_and_interpolate(
                src,
                window,
                band=band,
                target_cell_size=target_cell_size,
                resampling=resampling,
                max_search_distance=max_search_distance,
            )

            # Step 4: clip back to original tile geometry and write GeoTIFF.
            out_path = out_dir / f"{tile_id}.tif"
            clip_to_tile_and_write(
                tile_geom=tile_geom,
                data=filled,
                transform=out_transform,
                profile=out_profile,
                out_path=out_path,
            )
            result.at[idx, "out_path"] = str(out_path)

    return result
