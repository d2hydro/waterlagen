"""Lossless COG export of decoded DEM heights as Float32 metres."""

from math import ceil
from pathlib import Path

import numpy as np
import rasterio
from osgeo import gdal
from pyproj import CRS
from pyproj.crs import CompoundCRS
from tqdm.auto import tqdm

from waterlagen._filesystem import replace_file
from waterlagen.logger import get_logger
from waterlagen.raster.vrt import create_cog_file, create_vrt_file

logger = get_logger(__name__)


def _validate_dem_metadata(path: Path, *, expected_scale: float | None = None) -> None:
    """Check height metadata, including scale preservation and the NAP datum."""
    with gdal.Open(str(path)) as dataset:
        if dataset.RasterCount != 1:
            raise ValueError("DEM must have exactly one height band")
        band = dataset.GetRasterBand(1)
        scale = band.GetScale()
        offset = band.GetOffset()
        if scale is None or not np.isfinite(scale) or scale <= 0:
            raise ValueError("DEM must declare a finite positive scale")
        if expected_scale is not None and scale != expected_scale:
            raise ValueError("DEM scale differs from the expected height scale")
        if offset is not None and not np.isfinite(offset):
            raise ValueError("DEM offset must be finite")
        if band.GetUnitType() != "m":
            raise ValueError("DEM must declare unit 'm' for decoded heights")
        crs = CRS.from_wkt(dataset.GetProjection())
        if not crs.is_compound or crs.sub_crs_list[-1] != CRS.from_epsg(5709):
            raise ValueError("DEM CRS must include NAP height (EPSG:5709)")


def _create_dem_vrt(target: Path, files: list[Path]) -> Path:
    """Publish NAP metadata without resampling or changing stored heights."""
    temporary = target.with_suffix(".publish.vrt")
    with rasterio.open(files[0]) as source:
        expected_scale = source.scales[0]
    try:
        logger.info("Writing DEM height metadata (unit m, NAP datum) to %s", target)
        create_vrt_file(temporary, files=files)
        with gdal.Open(str(temporary), gdal.GA_Update) as dataset:
            source_crs = CRS.from_wkt(dataset.GetProjection())
            # Preserve the configured horizontal grid; RD + NAP is EPSG:7415.
            height_crs = source_crs
            if not source_crs.is_compound:
                height_crs = CompoundCRS(
                    name=f"{source_crs.name} + NAP height",
                    components=[source_crs, CRS.from_epsg(5709)],
                )
            dataset.SetProjection(height_crs.to_wkt())
            dataset.GetRasterBand(1).SetUnitType("m")
        _validate_dem_metadata(temporary, expected_scale=expected_scale)
        replace_file(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def validate_float_dem(source_path: Path, float_path: Path) -> None:
    """Check the float grid, validity mask and decoded values block by block.

    Parameters
    ----------
    source_path, float_path : pathlib.Path
        Stored DEM and its Float32 export. Values may differ only by Float32
        rounding; the float raster must have identity scale and offset and
        declare unit ``m`` for the decoded heights.
    """
    with rasterio.open(source_path) as source, rasterio.open(float_path) as target:
        if (source.shape, source.transform, source.crs) != (
            target.shape,
            target.transform,
            target.crs,
        ) or (target.dtypes, target.scales, target.offsets) != (
            ("float32",),
            (1.0,),
            (0.0,),
        ):
            raise ValueError("Float DEM grid, dtype or scale/offset differs")
        if target.nodata is None or not np.isnan(target.nodata):
            raise ValueError("Float DEM must declare NaN NoData")
        if target.units != ("m",):
            raise ValueError("Float DEM must declare unit 'm'")
        block_height, block_width = source.block_shapes[0]
        block_count = ceil(source.height / block_height) * ceil(
            source.width / block_width
        )
        for _, window in tqdm(
            source.block_windows(1),
            total=block_count,
            desc=f"Controle {float_path.name}",
            unit="blok",
        ):
            stored = source.read(1, window=window, masked=True)
            decoded = target.read(1, window=window, masked=True)
            invalid = np.ma.getmaskarray(stored) | ~np.isfinite(stored.data)
            if not np.array_equal(invalid, np.ma.getmaskarray(decoded)):
                raise ValueError("Float DEM validity mask differs")
            expected = (
                stored.data[~invalid].astype("float64") * source.scales[0]
                + source.offsets[0]
            ).astype("float32")
            if not np.isfinite(expected).all() or not np.array_equal(
                decoded.data[~invalid], expected
            ):
                raise ValueError("Float DEM values differ from decoded stored heights")


def create_float_dem(source_path: Path, target_path: Path) -> Path:
    """Create a Float32 COG from a stored DEM without altering the source.

    Parameters
    ----------
    source_path, target_path : pathlib.Path
        Validated stored DEM and destination. Scale and offset are applied to
        valid values; NoData becomes NaN. Existing output is replaced only after
        full validation. Overviews are rebuilt from decoded elevations.

    Returns
    -------
    pathlib.Path
        Validated Float32 COG, compressed with ZSTD and floating-point prediction.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    vrt_path = target_path.with_suffix(".tmp.vrt")
    staged = target_path.with_name(f"{target_path.stem}.publish.tif")
    dataset = None
    preserve_staged = False
    try:
        logger.info("Decoding stored DEM heights to Float32: %s", target_path)
        dataset = gdal.Translate(
            str(vrt_path),
            str(source_path),
            format="VRT",
            outputType=gdal.GDT_Float32,
            unscale=True,
            noData=float("nan"),
        )
        if dataset is None:
            raise RuntimeError("Could not create decoded DEM VRT")
        band = dataset.GetRasterBand(1)
        band.SetScale(1.0)
        band.SetOffset(0.0)
        band.SetUnitType("m")
        band = None
        dataset = None
        create_cog_file(
            vrt_path,
            staged,
            overwrite=True,
            overview_resampling="average",
            floating_point_predictor=True,
            regenerate_overviews=True,
        )
        validate_float_dem(source_path, staged)
        replace_file(staged, target_path)
    except PermissionError:
        preserve_staged = True
        logger.error("Float export retained for recovery: %s", staged)
        raise
    finally:
        dataset = None
        vrt_path.unlink(missing_ok=True)
        if not preserve_staged:
            staged.unlink(missing_ok=True)
    return target_path
