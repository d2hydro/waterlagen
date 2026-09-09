"""Raster preparation for afwateringseenheden calculations."""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.fill import fillnodata
from rasterio.warp import reproject
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from waterlagen import _geopandas as wgpd
from waterlagen import datastore as default_datastore
from waterlagen._crs import same_crs
from waterlagen.datastore import DataStore
from waterlagen.logger import get_logger
from waterlagen.raster.grid import RasterGrid
from waterlagen.settings import settings

logger = get_logger(__name__)

DEM_FILENAME = "dem_2m.tif"
HYDROOBJECT_SEGMENT_FILENAME = "hydroobject_segment.tif"


@dataclass(frozen=True)
class WatersysteemRasters:
    """Paths to the aligned rasters prepared for one spatial square."""

    dem_path: Path
    hydroobject_segment_path: Path


def _temporary_raster_path(target_path: Path) -> Path:
    """Create an unused temporary GeoTIFF path beside its target."""
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=target_path.suffix,
        dir=target_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink(missing_ok=True)
    return temporary_path


def _grid_for_square(
    ruimtelijk_vierkant: BaseGeometry,
    *,
    resolution_m: float,
) -> RasterGrid:
    """Create an exact raster grid for a square aligned to its requested resolution."""
    if ruimtelijk_vierkant.is_empty:
        raise ValueError("ruimtelijk_vierkant must not be empty")
    if resolution_m <= 0:
        raise ValueError("resolution_m must be greater than zero")

    minx, miny, maxx, maxy = ruimtelijk_vierkant.bounds
    width_m = maxx - minx
    height_m = maxy - miny
    if not np.isclose(width_m, height_m):
        raise ValueError("ruimtelijk_vierkant must have equal width and height")
    width = round(width_m / resolution_m)
    height = round(height_m / resolution_m)
    if width <= 0 or height <= 0:
        raise ValueError("ruimtelijk_vierkant must be larger than one raster cell")
    if not np.isclose(width * resolution_m, width_m) or not np.isclose(
        height * resolution_m,
        height_m,
    ):
        raise ValueError(
            "ruimtelijk_vierkant bounds must align with the requested resolution"
        )

    return RasterGrid.from_bounds(
        (minx, miny, maxx, maxy),
        resolution=resolution_m,
        crs=settings.crs,
    )


def _fill_dem_nodata(data: np.ndarray) -> np.ndarray:
    """Fill non-finite DEM cells with rasterio's inverse-distance algorithm."""
    valid_cells = np.isfinite(data)
    if valid_cells.all():
        return data
    if not valid_cells.any():
        raise ValueError("DEM has no finite elevation values to fill NoData cells")

    max_search_distance = float(np.hypot(*data.shape))
    filled_data = fillnodata(
        data,
        mask=valid_cells,
        max_search_distance=max_search_distance,
    )
    remaining = int((~np.isfinite(filled_data)).sum())
    if remaining:
        raise ValueError(
            "DEM NoData filling did not complete; "
            f"{remaining} non-finite cell(s) remain"
        )
    return filled_data


def _validate_source_coverage(
    source: rasterio.io.DatasetReader,
    grid: RasterGrid,
) -> None:
    """Raise a clear error when a project-CRS square is outside the AHN VRT."""
    if not same_crs(source.crs, grid.crs):
        return
    if box(*source.bounds).intersects(box(*grid.bounds)):
        return
    raise ValueError(
        "Requested square "
        f"{grid.bounds} does not intersect AHN VRT extent {tuple(source.bounds)}"
    )


def _resample_dem(source: rasterio.io.DatasetReader, grid: RasterGrid) -> np.ndarray:
    """Resample the raw DEM values to the target grid and fill all NoData cells."""
    _validate_source_coverage(source, grid)
    data = np.full((grid.height, grid.width), np.nan, dtype=np.float64)
    reproject(
        source=rasterio.band(source, 1),
        destination=data,
        src_transform=source.transform,
        src_crs=source.crs,
        src_nodata=source.nodata,
        dst_transform=grid.transform,
        dst_crs=grid.crs,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    return _fill_dem_nodata(data)


def _features_in_project_crs(
    path: Path,
    *,
    layer_name: str,
    grid: RasterGrid,
    fid_as_index: bool = False,
) -> gpd.GeoDataFrame:
    """Read a watersysteem layer and normalize it to the raster CRS."""
    features = wgpd.read_file(
        path,
        layer=layer_name,
        bbox=grid.bounds,
        fid_as_index=fid_as_index,
    )
    if features.crs is None:
        raise ValueError(f"Layer '{layer_name}' has no CRS")
    if not same_crs(features.crs, grid.crs):
        features = features.to_crs(grid.crs)
    return features


def _rasterize_mask(features: gpd.GeoDataFrame, grid: RasterGrid) -> np.ndarray:
    """Rasterize non-empty geometries as a boolean mask on the target grid."""
    shapes = [
        (geometry, 1)
        for geometry in features.geometry
        if geometry is not None and not geometry.is_empty
    ]
    if not shapes:
        return np.zeros((grid.height, grid.width), dtype=bool)
    return rasterize(
        shapes,
        out_shape=(grid.height, grid.width),
        transform=grid.transform,
        fill=0,
        dtype=np.uint8,
        all_touched=False,
    ).astype(bool)


def _burn_depth_in_stored_units(burn_depth_m: float, *, scale: float) -> float:
    """Convert a physical burn depth in metres to the DEM storage units."""
    if burn_depth_m < 0:
        raise ValueError("burn_depth_m must not be negative")
    if not np.isfinite(scale) or scale == 0:
        raise ValueError("DEM scale must be a finite, non-zero value")
    return burn_depth_m / scale


def _cast_dem_data(data: np.ndarray, *, dtype: str) -> np.ndarray:
    """Cast interpolated raw elevation values back to the source storage type."""
    target_dtype = np.dtype(dtype)
    if np.issubdtype(target_dtype, np.integer):
        limits = np.iinfo(target_dtype)
        rounded = np.rint(data)
        if (rounded < limits.min).any() or (rounded > limits.max).any():
            raise ValueError(f"Burned DEM values do not fit in {target_dtype}")
        return rounded.astype(target_dtype)
    return data.astype(target_dtype)


def _dem_profile(source: rasterio.io.DatasetReader, grid: RasterGrid) -> dict:
    """Create a GeoTIFF profile that preserves the source DEM data type and nodata."""
    return {
        "driver": "GTiff",
        "count": 1,
        "dtype": source.dtypes[0],
        "nodata": source.nodata,
        "width": grid.width,
        "height": grid.height,
        "transform": grid.transform,
        "crs": grid.crs,
        "compress": source.profile.get("compress", "deflate"),
    }


def _write_dem(
    target_path: Path,
    *,
    data: np.ndarray,
    profile: dict,
    scales: tuple[float, ...],
    offsets: tuple[float, ...],
) -> None:
    """Write a DEM while retaining its source scale and offset metadata."""
    with rasterio.open(target_path, "w", **profile) as destination:
        destination.scales = scales
        destination.offsets = offsets
        destination.write(data, 1)


def _segment_raster(
    segments: gpd.GeoDataFrame,
    grid: RasterGrid,
) -> np.ndarray:
    """Rasterize hydroobject segment FIDs, reserving zero for cells without a segment."""
    shapes = [
        (geometry, int(fid))
        for fid, geometry in zip(segments.index, segments.geometry)
        if geometry is not None and not geometry.is_empty
    ]
    if not shapes:
        return np.zeros((grid.height, grid.width), dtype=np.int32)
    return rasterize(
        shapes,
        out_shape=(grid.height, grid.width),
        transform=grid.transform,
        fill=0,
        dtype=np.int32,
        all_touched=False,
    )


def _write_segment_raster(
    target_path: Path, *, data: np.ndarray, grid: RasterGrid
) -> None:
    """Write one aligned hydroobject-segment identifier raster."""
    profile = {
        "driver": "GTiff",
        "count": 1,
        "dtype": "int32",
        "nodata": 0,
        "width": grid.width,
        "height": grid.height,
        "transform": grid.transform,
        "crs": grid.crs,
        "compress": "deflate",
    }
    with rasterio.open(target_path, "w", **profile) as destination:
        destination.write(data, 1)


def _validate_rasters(
    dem_path: Path,
    segment_path: Path,
    *,
    grid: RasterGrid,
) -> None:
    """Ensure completed output rasters share the requested grid and DEM has no gaps."""
    with rasterio.open(dem_path) as dem, rasterio.open(segment_path) as segment:
        for raster_path, dataset in ((dem_path, dem), (segment_path, segment)):
            if dataset.count != 1:
                raise ValueError(f"{raster_path} must contain exactly one band")
            if dataset.width != grid.width or dataset.height != grid.height:
                raise ValueError(
                    f"{raster_path} does not match the requested grid size"
                )
            if not same_crs(dataset.crs, grid.crs):
                raise ValueError(f"{raster_path} does not match the requested CRS")
            if dataset.transform != grid.transform:
                raise ValueError(
                    f"{raster_path} does not match the requested alignment"
                )
        if np.ma.getmaskarray(dem.read(1, masked=True)).any():
            raise ValueError(f"{dem_path} still contains NoData cells")


def prepare_watersysteem_rasters(
    ruimtelijk_vierkant: BaseGeometry,
    *,
    burn_depth_m: float,
    ahn_vrt_path: Path | None = None,
    watersysteem_path: Path | None = None,
    output_dir: Path | None = None,
    data_store: DataStore | None = None,
    resolution_m: float = 2.0,
    overwrite: bool = False,
) -> WatersysteemRasters:
    """Create aligned DEM and hydroobject-segment rasters for one spatial square.

    The AHN ``dtm_05`` VRT is resampled to a 2 by 2 metre grid by default.
    Missing elevation cells are filled with ``rasterio.fill.fillnodata`` using
    a search distance spanning the full raster, so the final DEM has no NoData
    holes. Primary and secondary hydroobjects are rasterized separately.
    The primary mask has priority, so its two-times burn depth is not added to
    the one-times secondary depth in overlapping cells. The companion segment
    raster stores GeoPackage feature IDs, with zero denoting no segment.

    Parameters
    ----------
    ruimtelijk_vierkant : shapely.geometry.base.BaseGeometry
        Square output extent in :data:`waterlagen.settings.settings.crs`. Its
        width and height must be equal and exactly divisible by ``resolution_m``.
    burn_depth_m : float
        Physical burn depth in metres. Primary hydroobjects are lowered by two
        times this value and secondary hydroobjects by one times this value.
    ahn_vrt_path : Path, optional
        AHN source VRT. Defaults to ``datastore.ahn_dir / 'dtm_05' /
        'dtm_05.vrt'``.
    watersysteem_path : Path, optional
        GeoPackage containing ``hydroobject_primair``,
        ``hydroobject_secundair``, and ``hydroobject_segment``. Defaults to
        ``datastore.afwateringseenheden_path / 'watersysteem.gpkg'``.
    output_dir : Path, optional
        Directory for ``dem_2m.tif`` and ``hydroobject_segment.tif``. Defaults
        to ``datastore.afwateringseenheden_path / 'rasters'``.
    data_store : waterlagen.datastore.DataStore, optional
        Datastore used for all default paths.
    resolution_m : float, optional
        Cell size in project-CRS metres, by default 2.
    overwrite : bool, optional
        Whether existing validated raster pairs are regenerated. With False,
        both existing valid outputs are reused.

    Returns
    -------
    WatersysteemRasters
        Paths to the validated DEM and hydroobject-segment GeoTIFFs.

    Side Effects
    ------------
    Writes both GeoTIFFs through temporary files beside their targets. Each
    completed temporary raster is validated before it atomically replaces its
    corresponding target.
    """
    data_store = data_store or default_datastore
    grid = _grid_for_square(ruimtelijk_vierkant, resolution_m=resolution_m)
    ahn_vrt_path = Path(ahn_vrt_path or data_store.ahn_dir / "dtm_05" / "dtm_05.vrt")
    watersysteem_path = Path(
        watersysteem_path or data_store.afwateringseenheden_path / "watersysteem.gpkg"
    )
    output_dir = Path(output_dir or data_store.afwateringseenheden_path / "rasters")
    dem_path = output_dir / DEM_FILENAME
    segment_path = output_dir / HYDROOBJECT_SEGMENT_FILENAME
    result = WatersysteemRasters(dem_path, segment_path)

    if dem_path.exists() and segment_path.exists() and not overwrite:
        _validate_rasters(dem_path, segment_path, grid=grid)
        logger.info("Reusing validated watersysteem rasters in %s", output_dir)
        return result

    if not ahn_vrt_path.exists():
        raise FileNotFoundError(f"AHN VRT not found: {ahn_vrt_path}")
    if not watersysteem_path.exists():
        raise FileNotFoundError(
            f"Watersysteem GeoPackage not found: {watersysteem_path}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    temporary_dem_path = _temporary_raster_path(dem_path)
    temporary_segment_path = _temporary_raster_path(segment_path)
    try:
        logger.info("Reading AHN VRT %s for square %s", ahn_vrt_path, grid.bounds)
        with rasterio.open(ahn_vrt_path) as source:
            if source.crs is None:
                raise ValueError(f"AHN VRT has no CRS: {ahn_vrt_path}")
            dem_data = _resample_dem(source, grid)
            scale = source.scales[0]
            primary = _features_in_project_crs(
                watersysteem_path,
                layer_name="hydroobject_primair",
                grid=grid,
            )
            secondary = _features_in_project_crs(
                watersysteem_path,
                layer_name="hydroobject_secundair",
                grid=grid,
            )
            primary_mask = _rasterize_mask(primary, grid)
            secondary_mask = _rasterize_mask(secondary, grid)
            burn_depth = _burn_depth_in_stored_units(burn_depth_m, scale=scale)
            burn_values = np.where(
                primary_mask,
                2 * burn_depth,
                np.where(secondary_mask, burn_depth, 0),
            )
            burned_dem = _cast_dem_data(
                dem_data - burn_values,
                dtype=source.dtypes[0],
            )
            _write_dem(
                temporary_dem_path,
                data=burned_dem,
                profile=_dem_profile(source, grid),
                scales=source.scales,
                offsets=source.offsets,
            )

        logger.info("Rasterizing hydroobject_segment from %s", watersysteem_path)
        segments = _features_in_project_crs(
            watersysteem_path,
            layer_name="hydroobject_segment",
            grid=grid,
            fid_as_index=True,
        )
        _write_segment_raster(
            temporary_segment_path,
            data=_segment_raster(segments, grid),
            grid=grid,
        )
        logger.info("Validating watersysteem rasters for square %s", grid.bounds)
        _validate_rasters(temporary_dem_path, temporary_segment_path, grid=grid)
        temporary_dem_path.replace(dem_path)
        temporary_segment_path.replace(segment_path)
    except Exception:
        temporary_dem_path.unlink(missing_ok=True)
        temporary_segment_path.unlink(missing_ok=True)
        raise

    logger.info("Prepared watersysteem rasters in %s", output_dir)
    return result
