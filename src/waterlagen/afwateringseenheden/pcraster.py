"""PCRaster integration for afwateringseenheden calculations."""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Literal

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape

from waterlagen import _geopandas as wgpd
from waterlagen import datastore as default_datastore
from waterlagen._crs import same_crs
from waterlagen._geopackage import write_geopackage_layer
from waterlagen.datastore import DataStore
from waterlagen.logger import get_logger

from .raster import WatersysteemRasters

logger = get_logger(__name__)

LDD_FILENAME = "ldd.tif"
SUBCATCHMENTS_FILENAME = "subcatchments.tif"
SUBCATCHMENTS_GPKG_FILENAME = "afwateringseenheden.gpkg"
SUBCATCHMENTS_LAYER = "afvoergebiedaanvoergebied"
LDD_NODATA = 255
SUBCATCHMENTS_NODATA = -999


@dataclass(frozen=True)
class SubcatchmentResult:
    """Files and polygons produced by one subcatchment calculation."""

    ldd_path: Path
    subcatchments_path: Path
    afwateringseenheden_path: Path
    subcatchments: gpd.GeoDataFrame


def _temporary_path(target_path: Path) -> Path:
    """Create an unused temporary path beside a target file."""
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=target_path.suffix,
        dir=target_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink(missing_ok=True)
    return temporary_path


def _validate_input_grid(
    dem: rasterio.io.DatasetReader,
    hydroobject_segment: rasterio.io.DatasetReader,
) -> None:
    """Ensure PCRaster inputs have one identical north-up GeoTIFF grid."""
    if dem.count != 1 or hydroobject_segment.count != 1:
        raise ValueError("DEM and hydroobject_segment must each have one band")
    if (
        dem.width != hydroobject_segment.width
        or dem.height != hydroobject_segment.height
    ):
        raise ValueError("DEM and hydroobject_segment do not have the same dimensions")
    if dem.crs is None or hydroobject_segment.crs is None:
        raise ValueError("DEM and hydroobject_segment must have a CRS")
    if not same_crs(dem.crs, hydroobject_segment.crs):
        raise ValueError("DEM and hydroobject_segment do not have the same CRS")
    if dem.transform != hydroobject_segment.transform:
        raise ValueError("DEM and hydroobject_segment do not have the same alignment")
    if dem.transform.b != 0 or dem.transform.d != 0:
        raise ValueError("PCRaster requires a north-up raster grid")
    if not np.isclose(abs(dem.transform.a), abs(dem.transform.e)):
        raise ValueError("PCRaster requires square raster cells")


def _set_clone_from_dataset(
    dataset: rasterio.io.DatasetReader,
    pcraster: ModuleType,
) -> None:
    """Set a PCRaster clone directly from an open north-up GeoTIFF dataset."""
    pcraster.setclone(
        dataset.height,
        dataset.width,
        abs(dataset.transform.a),
        dataset.transform.c,
        dataset.transform.f,
    )
    pcraster.setglobaloption("unittrue")
    pcraster.setglobaloption("lddin")


def _max_fill_depth_in_stored_units(
    max_fill_depth_m: float,
    *,
    scale: float,
) -> float:
    """Convert a physical maximum fill depth to stored DEM value units."""
    if max_fill_depth_m < 0:
        raise ValueError("max_fill_depth_m must not be negative")
    if not np.isfinite(scale) or scale == 0:
        raise ValueError("DEM scale must be a finite, non-zero value")
    return max_fill_depth_m / scale


def _calculate_pcraster_maps(
    dem: rasterio.io.DatasetReader,
    hydroobject_segment: rasterio.io.DatasetReader,
    *,
    max_fill_depth_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Calculate LDD and subcatchments with in-memory PCRaster maps."""
    pcraster = require_pcraster()
    _set_clone_from_dataset(dem, pcraster)

    elevation = dem.read(1).astype(np.float64)
    if not np.isfinite(elevation).all():
        raise ValueError("DEM contains non-finite values")
    water_segments = hydroobject_segment.read(1).astype(np.int32)
    if not np.any(water_segments != hydroobject_segment.nodata):
        raise ValueError("hydroobject_segment contains no segment cells")

    elevation_map = pcraster.numpy2pcr(pcraster.Scalar, elevation, dem.nodata)
    water_segments_map = pcraster.numpy2pcr(
        pcraster.Nominal,
        water_segments,
        hydroobject_segment.nodata,
    )
    ldd = pcraster.lddcreate(
        elevation_map,
        _max_fill_depth_in_stored_units(
            max_fill_depth_m,
            scale=dem.scales[0],
        ),
        1e31,
        1e31,
        1e31,
    )
    catchments = pcraster.subcatchment(ldd, water_segments_map)
    return (
        pcraster.pcr2numpy(ldd, LDD_NODATA).astype(np.uint8),
        pcraster.pcr2numpy(catchments, SUBCATCHMENTS_NODATA).astype(np.int32),
    )


def _write_raster(
    target_path: Path,
    *,
    data: np.ndarray,
    reference: rasterio.io.DatasetReader,
    dtype: str,
    nodata: int,
) -> None:
    """Write one single-band GeoTIFF with the reference grid metadata."""
    profile = {
        "driver": "GTiff",
        "count": 1,
        "dtype": dtype,
        "nodata": nodata,
        "width": reference.width,
        "height": reference.height,
        "transform": reference.transform,
        "crs": reference.crs,
        "compress": "deflate",
    }
    with rasterio.open(target_path, "w", **profile) as destination:
        destination.write(data, 1)


def _validate_output_grid(
    path: Path,
    *,
    reference: rasterio.io.DatasetReader,
) -> None:
    """Ensure a derived GeoTIFF still uses its input grid without changes."""
    with rasterio.open(path) as result:
        if result.width != reference.width or result.height != reference.height:
            raise ValueError(f"{path} does not match the DEM dimensions")
        if result.transform != reference.transform:
            raise ValueError(f"{path} does not match the DEM alignment")
        if result.crs is None or not same_crs(result.crs, reference.crs):
            raise ValueError(f"{path} does not match the DEM CRS")


def _segment_ids_by_fid(watersysteem_path: Path) -> dict[int, str]:
    """Read the hydroobject-segment GeoPackage FID to segment-ID relation."""
    segments = wgpd.read_file(
        watersysteem_path,
        layer="hydroobject_segment",
        fid_as_index=True,
    )
    if "segment_id" not in segments.columns:
        raise ValueError("hydroobject_segment has no segment_id column")
    if segments["segment_id"].isna().any():
        raise ValueError("hydroobject_segment has missing segment_id values")
    return {
        int(fid): str(segment_id) for fid, segment_id in segments["segment_id"].items()
    }


def _polygonize_subcatchments(
    data: np.ndarray,
    *,
    transform,
    crs,
    segment_ids_by_fid: dict[int, str],
) -> gpd.GeoDataFrame:
    """Polygonize valid segment FIDs and resolve each to its segment ID."""
    valid_fids = np.fromiter(segment_ids_by_fid, dtype=np.int32)
    values = set(np.unique(data)) - {SUBCATCHMENTS_NODATA, 0}
    unknown_fids = values - set(valid_fids)
    if unknown_fids:
        unknown = min(unknown_fids)
        raise ValueError(
            "Subcatchment raster contains a hydroobject_segment FID "
            f"without a matching segment_id: {unknown}"
        )

    mask = np.isin(data, valid_fids)
    polygons: list[dict[str, int | str]] = []
    geometries = []
    for geometry, value in shapes(data, mask=mask, transform=transform):
        segment_fid = int(value)
        polygons.append(
            {
                "segment_fid": segment_fid,
                "segment_id": segment_ids_by_fid[segment_fid],
            }
        )
        geometries.append(shape(geometry))
    if not polygons:
        raise ValueError("Subcatchment raster contains no catchments")
    return gpd.GeoDataFrame(polygons, geometry=geometries, crs=crs)


def _write_subcatchment_geopackage(
    output_path: Path,
    subcatchments: gpd.GeoDataFrame,
) -> None:
    """Atomically write the subcatchment layer to its square-specific GeoPackage."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _temporary_path(output_path)
    try:
        write_geopackage_layer(
            subcatchments,
            temporary_path,
            layer_name=SUBCATCHMENTS_LAYER,
            mode="w",
        )
        written = wgpd.read_file(temporary_path, layer=SUBCATCHMENTS_LAYER)
        if len(written) != len(subcatchments):
            raise ValueError("Subcatchment GeoPackage layer validation failed")
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def calculate_subcatchments(
    rasters: WatersysteemRasters,
    *,
    watersysteem_path: Path | None = None,
    data_store: DataStore | None = None,
    max_fill_depth_m: float = 50.0,
    engine: Literal["pcraster"] = "pcraster",
) -> SubcatchmentResult:
    """Calculate subcatchments that drain to prepared hydroobject segments.

    Parameters
    ----------
    rasters : WatersysteemRasters
        Aligned DEM and hydroobject-segment raster outputs.
    watersysteem_path : Path, optional
        GeoPackage containing ``hydroobject_segment``.
    data_store : waterlagen.datastore.DataStore, optional
        Datastore used for the default watersysteem path.
    max_fill_depth_m : float, optional
        Maximum depression fill depth in metres, by default 50.
    engine : {"pcraster"}, optional
        Flow-direction engine. Only PCRaster is implemented.

    Returns
    -------
    SubcatchmentResult
        LDD, subcatchment and GeoPackage output paths plus the polygons.
    """
    if engine != "pcraster":
        raise ValueError(f"Unsupported subcatchment engine: {engine}")

    data_store = data_store or default_datastore
    watersysteem_path = Path(
        watersysteem_path or data_store.afwateringseenheden_path / "watersysteem.gpkg"
    )
    if not watersysteem_path.exists():
        raise FileNotFoundError(
            f"Watersysteem GeoPackage not found: {watersysteem_path}"
        )
    if not rasters.dem_path.exists() or not rasters.hydroobject_segment_path.exists():
        raise FileNotFoundError(
            "Prepared DEM and hydroobject_segment GeoTIFFs are required"
        )

    output_directory = rasters.dem_path.parent
    ldd_path = output_directory / LDD_FILENAME
    subcatchments_path = output_directory / SUBCATCHMENTS_FILENAME
    afwateringseenheden_path = output_directory / SUBCATCHMENTS_GPKG_FILENAME
    output_directory.mkdir(parents=True, exist_ok=True)
    temporary_ldd_path = _temporary_path(ldd_path)
    temporary_subcatchments_path = _temporary_path(subcatchments_path)
    try:
        logger.info("Calculating LDD from %s", rasters.dem_path)
        with (
            rasterio.open(rasters.dem_path) as dem,
            rasterio.open(rasters.hydroobject_segment_path) as hydroobject_segment,
        ):
            _validate_input_grid(dem, hydroobject_segment)
            ldd_data, subcatchment_data = _calculate_pcraster_maps(
                dem,
                hydroobject_segment,
                max_fill_depth_m=max_fill_depth_m,
            )
            _write_raster(
                temporary_ldd_path,
                data=ldd_data,
                reference=dem,
                dtype="uint8",
                nodata=LDD_NODATA,
            )
            _write_raster(
                temporary_subcatchments_path,
                data=subcatchment_data,
                reference=dem,
                dtype="int32",
                nodata=SUBCATCHMENTS_NODATA,
            )
            _validate_output_grid(temporary_ldd_path, reference=dem)
            _validate_output_grid(temporary_subcatchments_path, reference=dem)
            subcatchments = _polygonize_subcatchments(
                subcatchment_data,
                transform=dem.transform,
                crs=dem.crs,
                segment_ids_by_fid=_segment_ids_by_fid(watersysteem_path),
            )

        _write_subcatchment_geopackage(afwateringseenheden_path, subcatchments)
        temporary_ldd_path.replace(ldd_path)
        temporary_subcatchments_path.replace(subcatchments_path)
    except Exception:
        temporary_ldd_path.unlink(missing_ok=True)
        temporary_subcatchments_path.unlink(missing_ok=True)
        raise

    logger.info(
        "Calculated %s subcatchments and wrote them to %s",
        len(subcatchments),
        afwateringseenheden_path,
    )
    return SubcatchmentResult(
        ldd_path,
        subcatchments_path,
        afwateringseenheden_path,
        subcatchments,
    )


def require_pcraster() -> ModuleType:
    """Import PCRaster or raise an actionable installation error."""
    try:
        import pcraster
    except ImportError as exc:
        raise RuntimeError(
            "PCRaster is required for afwateringseenheden. "
            "Run `pixi run --environment afwateringseenheden python ...`."
        ) from exc
    return pcraster
