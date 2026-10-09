import json
from contextlib import nullcontext
from math import isnan
from pathlib import Path

from osgeo import gdal, osr
from tqdm.auto import tqdm

from waterlagen._filesystem import replace_file
from waterlagen._production import _file_identity
from waterlagen.logger import get_logger

logger = get_logger(__name__)

gdal.UseExceptions()
gdal.SetConfigOption("GDAL_NUM_THREADS", "ALL_CPUS")

COG_CREATION_OPTIONS = (
    "COMPRESS=ZSTD",
    "LEVEL=9",
    "BLOCKSIZE=512",
    "OVERVIEW_RESAMPLING=NEAREST",
    "BIGTIFF=IF_SAFER",
    "NUM_THREADS=ALL_CPUS",
)


def create_vrt_file(
    vrt_file: Path,
    directory: Path | list[Path] | None = None,
    *,
    files: list[Path] | None = None,
) -> Path:
    """Create a mosaic, with later sources taking precedence over earlier ones.

    Parameters
    ----------
    vrt_file : pathlib.Path
        Destination VRT.
    directory : pathlib.Path or list of pathlib.Path, optional
        Directories containing TIFFs, in priority order.
    files : list of pathlib.Path, optional
        Explicit ordered sources, mutually exclusive with ``directory``.
        Explicit lists are validated and the VRT is replaced atomically.

    Returns
    -------
    pathlib.Path
        Destination VRT.
    """
    if files is not None:
        if directory is not None or not files:
            raise ValueError("Provide a nonempty files list or directories")
        if any(not path.is_file() for path in files):
            raise FileNotFoundError("A VRT source is missing")
        vrt_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = vrt_file.with_suffix(".tmp.vrt")
        try:
            dataset = gdal.BuildVRT(
                str(temporary),
                [str(path.resolve()) for path in files],
                options=gdal.BuildVRTOptions(strict=True, separate=False, bandList=[1]),
            )
            if dataset is None:
                raise ValueError("Could not build VRT")
            dataset.FlushCache()
            dataset = None
            temporary.replace(vrt_file)
        finally:
            temporary.unlink(missing_ok=True)
        logger.info("VRT file created %s", vrt_file)
        return vrt_file
    if directory is None:
        raise ValueError("Provide files or directory")
    if isinstance(directory, Path):
        directory = [directory]

    vrt_file = Path(vrt_file)

    tif_files = []
    for dir in directory:
        tif_files += [
            i.absolute().resolve().as_posix() for i in sorted(dir.glob("*.tif"))
        ]

    if len(tif_files) > 0:
        vrt_options = gdal.BuildVRTOptions(
            separate=False,
            addAlpha=False,
            bandList=[1],
        )

        ds = gdal.BuildVRT(
            destName=vrt_file.as_posix(),
            srcDSOrSrcDSTab=tif_files,
            options=vrt_options,
        )
        ds.FlushCache()
        logger.info(f"VRT file created {vrt_file}")
    else:
        logger.warning(f"No vrt-file created as no files exist in {directory}")

    return vrt_file


def list_tif_files_in_vrt_file(vrt_file: Path):
    """Return a list of files within a vrt-file."""
    vrt_file = Path(vrt_file)

    info = gdal.Info(vrt_file.as_posix(), format="json")

    return [Path(i) for i in info["files"] if i != vrt_file.as_posix()]


class _GdalProgressBar:
    def __init__(self, *, desc: str) -> None:
        self._progress = tqdm(total=100, desc=desc, unit="%")
        self._current = 0

    def callback(self, complete: float, message: str, data: object) -> int:
        value = max(0, min(100, round(complete * 100)))
        if value > self._current:
            self._progress.update(value - self._current)
            self._current = value
        return 1

    def finish(self) -> None:
        if self._current < 100:
            self._progress.update(100 - self._current)
            self._current = 100

    def close(self) -> None:
        self._progress.close()


def _open_gdal_dataset(path: Path):
    try:
        dataset = gdal.Open(path.as_posix(), getattr(gdal, "GA_ReadOnly", 0))
    except Exception as exc:
        raise ValueError(f"Could not open raster with GDAL: {path}") from exc
    if dataset is None:
        raise ValueError(f"Could not open raster with GDAL: {path}")
    return dataset


def _same_crs(left_wkt: str, right_wkt: str) -> bool:
    if not left_wkt and not right_wkt:
        return True
    if not left_wkt or not right_wkt:
        return False

    left = osr.SpatialReference()
    right = osr.SpatialReference()
    if left.ImportFromWkt(left_wkt) != 0 or right.ImportFromWkt(right_wkt) != 0:
        return left_wkt == right_wkt
    return bool(left.IsSame(right))


def _run_cog_validator(cog_file: Path) -> None:
    try:
        from osgeo_utils.samples.validate_cloud_optimized_geotiff import validate
    except ImportError:
        logger.warning("GDAL COG validation utility is not available")
        return

    try:
        validation_result = validate(cog_file.as_posix(), check_tiled=True)
    except Exception as exc:
        raise ValueError(f"COG validation failed for {cog_file}: {exc}") from exc
    errors = validation_result[0]
    if errors:
        message = "; ".join(str(error) for error in errors)
        raise ValueError(f"COG validation failed for {cog_file}: {message}")


def _validate_cog_file(cog_file: Path, vrt_dataset) -> None:
    if not cog_file.exists():
        raise ValueError(f"COG was not created: {cog_file}")

    cog_dataset = _open_gdal_dataset(cog_file)
    try:
        driver = cog_dataset.GetDriver()
        driver_name = driver.ShortName if driver is not None else None
        if driver_name != "GTiff":
            raise ValueError(
                f"COG validation failed for {cog_file}: expected GTiff driver, "
                f"got {driver_name!r}"
            )

        vrt_band = vrt_dataset.GetRasterBand(1)
        cog_band = cog_dataset.GetRasterBand(1)
        block_size = tuple(cog_band.GetBlockSize())
        if block_size != (512, 512):
            raise ValueError(
                f"COG validation failed for {cog_file}: expected 512 x 512 "
                f"blocks, got {block_size[0]} x {block_size[1]}"
            )

        if not _same_crs(
            vrt_dataset.GetProjectionRef(), cog_dataset.GetProjectionRef()
        ):
            raise ValueError(
                f"COG validation failed for {cog_file}: CRS differs from VRT"
            )

        if cog_band.DataType != vrt_band.DataType:
            raise ValueError(
                f"COG validation failed for {cog_file}: dtype differs from VRT"
            )

        cog_nodata, vrt_nodata = cog_band.GetNoDataValue(), vrt_band.GetNoDataValue()
        same_nodata = cog_nodata == vrt_nodata or (
            cog_nodata is not None
            and vrt_nodata is not None
            and isnan(cog_nodata)
            and isnan(vrt_nodata)
        )
        if not same_nodata:
            raise ValueError(
                f"COG validation failed for {cog_file}: nodata differs from VRT"
            )
        if (
            cog_dataset.RasterXSize,
            cog_dataset.RasterYSize,
            cog_dataset.GetGeoTransform(),
        ) != (
            vrt_dataset.RasterXSize,
            vrt_dataset.RasterYSize,
            vrt_dataset.GetGeoTransform(),
        ):
            raise ValueError(
                f"COG validation failed for {cog_file}: grid differs from VRT"
            )
        if (cog_band.GetScale() or 1.0, cog_band.GetOffset() or 0.0) != (
            vrt_band.GetScale() or 1.0,
            vrt_band.GetOffset() or 0.0,
        ):
            raise ValueError(
                f"COG validation failed for {cog_file}: scale/offset differs from VRT"
            )

        if cog_band.GetOverviewCount() < 1:
            raise ValueError(
                f"COG validation failed for {cog_file}: internal overviews are missing"
            )

        _run_cog_validator(cog_file)
    finally:
        cog_dataset = None


def validate_raster_attribute_table(
    raster_path: Path, expected: gdal.RasterAttributeTable, *, embedded: bool = False
) -> None:
    """Validate every RAT column and value, optionally ignoring all PAM sidecars.

    Parameters
    ----------
    raster_path : pathlib.Path
        Raster to reopen.
    expected : gdal.RasterAttributeTable
        Required schema and rows.
    embedded : bool
        Disable PAM while opening to verify the TIFF itself.
    """
    context = (
        gdal.config_option("GDAL_PAM_ENABLED", "NO") if embedded else nullcontext()
    )
    with context:
        dataset = _open_gdal_dataset(raster_path)
        try:
            actual = dataset.GetRasterBand(1).GetDefaultRAT()
            if actual is None or (actual.GetColumnCount(), actual.GetRowCount()) != (
                expected.GetColumnCount(),
                expected.GetRowCount(),
            ):
                raise ValueError(f"Missing or incomplete RAT: {raster_path}")
            for col in range(expected.GetColumnCount()):
                for method in ("GetNameOfCol", "GetTypeOfCol", "GetUsageOfCol"):
                    if getattr(actual, method)(col) != getattr(expected, method)(col):
                        raise ValueError(f"RAT schema differs: {raster_path}")
                for row in range(expected.GetRowCount()):
                    if actual.GetValueAsString(row, col) != expected.GetValueAsString(
                        row, col
                    ):
                        raise ValueError(f"RAT values differ: {raster_path}")
        finally:
            actual = None
            dataset = None


def create_cog_file(
    vrt_file: Path,
    cog_file: Path,
    *,
    overwrite: bool = False,
    show_progress: bool = True,
    overview_resampling: str = "nearest",
    floating_point_predictor: bool = False,
    regenerate_overviews: bool = False,
    raster_attribute_table: gdal.RasterAttributeTable | None = None,
) -> Path:
    """Create a Cloud Optimized GeoTIFF directly from a VRT file.

    Parameters
    ----------
    vrt_file, cog_file : pathlib.Path
        Input VRT and output COG.
    overwrite : bool
        Replace an existing COG only after successful validation.
    show_progress : bool
        Show GDAL conversion progress.
    overview_resampling : {"nearest", "average"}
        Overview resampling; use nearest for IDs/classes, average for elevation.

    floating_point_predictor : bool
        Use ZSTD floating-point prediction for the raster and overviews.
    regenerate_overviews : bool
        Build new overviews from full-resolution values instead of copying them.
    raster_attribute_table : osgeo.gdal.RasterAttributeTable, optional
        Embed this RAT during creation (GDAL >= 3.12), validating without PAM.

    Returns
    -------
    pathlib.Path
        Written or reused COG.
    """
    if raster_attribute_table is not None and int(gdal.VersionInfo()) < 3120000:
        raise RuntimeError("Embedded raster attribute tables require GDAL >= 3.12")
    if overview_resampling not in {"nearest", "average"}:
        raise ValueError("overview_resampling must be nearest or average")
    vrt_file = Path(vrt_file)
    cog_file = Path(cog_file)
    tmp_file = cog_file.with_name(f"{cog_file.stem}.tmp{cog_file.suffix}")

    if cog_file.exists() and not overwrite:
        if raster_attribute_table is not None:
            validate_raster_attribute_table(
                cog_file, raster_attribute_table, embedded=True
            )
        logger.info("Skipping existing COG file %s", cog_file)
        return cog_file

    if not vrt_file.exists():
        raise FileNotFoundError(f"VRT file does not exist: {vrt_file}")

    cog_file.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = tmp_file.with_name(tmp_file.name + ".ready.json")
    vrt_dataset = _open_gdal_dataset(vrt_file)
    export_identity = {
        "input": _file_identity(vrt_file),
        "overview_resampling": overview_resampling,
        "floating_point_predictor": floating_point_predictor,
        "regenerate_overviews": regenerate_overviews,
        "rat": None
        if raster_attribute_table is None
        else {
            "columns": [
                [
                    raster_attribute_table.GetNameOfCol(col),
                    raster_attribute_table.GetTypeOfCol(col),
                    raster_attribute_table.GetUsageOfCol(col),
                ]
                for col in range(raster_attribute_table.GetColumnCount())
            ],
            "rows": [
                [
                    raster_attribute_table.GetValueAsString(row, col)
                    for col in range(raster_attribute_table.GetColumnCount())
                ]
                for row in range(raster_attribute_table.GetRowCount())
            ],
        },
    }
    validated = False
    progress = (
        _GdalProgressBar(desc=f"VRT to COG: {cog_file.name}") if show_progress else None
    )
    try:
        if tmp_file.is_file() and checkpoint.is_file():
            pending = json.loads(checkpoint.read_text(encoding="utf-8"))
            if pending == {"export": export_identity, "file": _file_identity(tmp_file)}:
                _validate_cog_file(tmp_file, vrt_dataset)
                if raster_attribute_table is not None:
                    validate_raster_attribute_table(
                        tmp_file, raster_attribute_table, embedded=True
                    )
                validated = True
                logger.info(
                    "Publishing previously validated COG without reconversion: %s",
                    tmp_file,
                )
                replace_file(tmp_file, cog_file)
                checkpoint.unlink(missing_ok=True)
                return cog_file
        tmp_file.unlink(missing_ok=True)
        checkpoint.unlink(missing_ok=True)
        if raster_attribute_table is not None:
            # A memory VRT avoids adding PAM files or metadata to the source.
            vrt_dataset = gdal.Translate("", vrt_dataset, format="VRT")
            vrt_dataset.GetRasterBand(1).SetDefaultRAT(raster_attribute_table)
        vrt_band = vrt_dataset.GetRasterBand(1)
        translate_kwargs = {
            "format": "COG",
            "creationOptions": list(COG_CREATION_OPTIONS),
        }
        if overview_resampling != "nearest":
            translate_kwargs["creationOptions"] = [
                option
                if not option.startswith("OVERVIEW_RESAMPLING=")
                else "OVERVIEW_RESAMPLING=AVERAGE"
                for option in COG_CREATION_OPTIONS
            ]
        if floating_point_predictor:
            if vrt_band.DataType not in (gdal.GDT_Float32, gdal.GDT_Float64):
                raise ValueError(
                    "Floating-point prediction requires floating-point data"
                )
            translate_kwargs["creationOptions"].extend(
                ["PREDICTOR=FLOATING_POINT", "OVERVIEW_PREDICTOR=FLOATING_POINT"]
            )
        if regenerate_overviews:
            translate_kwargs["creationOptions"].append("OVERVIEWS=IGNORE_EXISTING")
        nodata = vrt_band.GetNoDataValue()
        if nodata is not None:
            translate_kwargs["noData"] = nodata
        if progress is not None:
            translate_kwargs["callback"] = progress.callback

        if (
            hasattr(vrt_dataset, "RasterXSize")
            and 1 < max(vrt_dataset.RasterXSize, vrt_dataset.RasterYSize) <= 512
        ):
            translate_kwargs["creationOptions"].append("OVERVIEW_COUNT=1")

        options = gdal.TranslateOptions(**translate_kwargs)
        context = (
            gdal.config_option("GTIFF_WRITE_RAT_TO_PAM", "NO")
            if raster_attribute_table is not None
            else nullcontext()
        )
        with context:
            dataset = gdal.Translate(
                destName=tmp_file.as_posix(),
                srcDS=vrt_dataset,
                options=options,
            )
            if dataset is None:
                raise RuntimeError(f"GDAL failed to create COG file: {tmp_file}")
            dataset.FlushCache()
            dataset = None
        if progress is not None:
            progress.finish()
            progress.close()
            progress = None

        logger.info("Validating COG after conversion: %s", tmp_file)
        _validate_cog_file(tmp_file, vrt_dataset)
        if raster_attribute_table is not None:
            validate_raster_attribute_table(
                tmp_file, raster_attribute_table, embedded=True
            )
        checkpoint.write_text(
            json.dumps({"export": export_identity, "file": _file_identity(tmp_file)}),
            encoding="utf-8",
        )
        validated = True
        logger.info("Publishing validated COG: %s", cog_file)
        replace_file(tmp_file, cog_file)
        checkpoint.unlink(missing_ok=True)
        logger.info("COG file created %s", cog_file)
        return cog_file
    except Exception:
        if validated:
            logger.error("Validated COG retained for recovery: %s", tmp_file)
        else:
            tmp_file.unlink(missing_ok=True)
            checkpoint.unlink(missing_ok=True)
        raise
    finally:
        if progress is not None:
            progress.close()
        vrt_dataset = None
