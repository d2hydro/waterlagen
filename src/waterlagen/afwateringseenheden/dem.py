"""Combine AHN with local NRW DGM1 after explicit RD/NAP conversion."""

from pathlib import Path

import numpy as np
import rasterio
from osgeo import gdal
from pyproj import Transformer
from rasterio.enums import Resampling

from waterlagen._crs import same_crs
from waterlagen._downloads import stream_download_to_temp
from waterlagen.logger import get_logger
from waterlagen.raster.config import RasterOutputConfig
from waterlagen.raster.grid import RasterGrid
from waterlagen.raster.overviews import build_raster_overviews

from ._coverage import _file_version, _vrt_sources
from .raster import _cast_dem_data, _dem_nodata, _dem_profile, _temporary_raster_path

logger = get_logger(__name__)

GRID_NAMES = (
    "de_bkg_gcg2016.tif",
    "nl_nsgi_nlgeo2018.tif",
    "nl_nsgi_rdtrans2018.tif",
)


def _rdnap_transformer(grid_dir: Path) -> Transformer:
    """Use local BKG/NSGI grids, never a ballpark or constant height offset."""
    grid_dir.mkdir(parents=True, exist_ok=True)
    for name in GRID_NAMES:
        path = grid_dir / name
        if not path.is_file():
            download = stream_download_to_temp(
                f"https://cdn.proj.org/{name}", path, timeout=60, logger=logger
            )
            try:
                if (
                    download.total_bytes is not None
                    and download.downloaded_bytes != download.total_bytes
                ):
                    raise ValueError(f"Onvolledig correctiegrid: {name}")
                with rasterio.open(download.target_path) as grid:
                    grid.read()
                download.target_path.replace(path)
            finally:
                download.target_path.unlink(missing_ok=True)

    german, dutch_height, dutch_horizontal = [
        (grid_dir / name).resolve().as_posix() for name in GRID_NAMES
    ]
    # DHHN2016 -> ETRS89 ellipsoid -> NAP; daarna ETRS89 -> RD.
    pipeline = (
        "+proj=pipeline "
        "+step +inv +proj=utm +zone=32 +ellps=GRS80 "
        f'+step +proj=vgridshift +grids="{german}" +multiplier=1 '
        f'+step +inv +proj=vgridshift +grids="{dutch_height}" +multiplier=1 '
        f'+step +inv +proj=hgridshift +grids="{dutch_horizontal}" '
        "+step +proj=sterea +lat_0=52.1561605555556 +lon_0=5.38763888888889 "
        "+k=0.9999079 +x_0=155000 +y_0=463000 +ellps=bessel"
    )
    return Transformer.from_pipeline(pipeline)


def _reuse_converted_tile(
    target_path: Path,
    ahn: rasterio.io.DatasetReader,
    conversion: dict[str, str],
) -> bool:
    """Reuse a matching readable tile; reject an outdated cache."""
    if not target_path.is_file():
        return False
    nodata = _dem_nodata(ahn)
    with rasterio.open(target_path) as existing:
        tags = existing.tags()
        same_nodata = existing.nodata == nodata or (
            existing.nodata is not None
            and nodata is not None
            and np.isnan(existing.nodata)
            and np.isnan(nodata)
        )
        if (
            all(tags.get(key) == value for key, value in conversion.items())
            and same_crs(existing.crs, ahn.crs)
            and existing.scales == ahn.scales
            and existing.offsets == ahn.offsets
            and existing.dtypes == ahn.dtypes
            and existing.res == (1.0, 1.0)
            and same_nodata
        ):
            existing.read(1)
            logger.info("Hergebruik RD/NAP-tegel %s", target_path.name)
            return True
    raise ValueError(
        f"Verouderde RD/NAP-tegel; kies een nieuwe cachemap: {target_path}"
    )


def _write_converted_tile(
    target_path: Path,
    data: np.ndarray,
    grid: RasterGrid,
    ahn: rasterio.io.DatasetReader,
    conversion: dict[str, str],
) -> Path:
    """Write with AHN storage metadata and publish after validating the pixels."""
    config = RasterOutputConfig()
    profile = _dem_profile(ahn, grid)
    profile.update(
        tiled=True, blockxsize=config.block_size, blockysize=config.block_size
    )
    temporary = _temporary_raster_path(target_path)
    try:
        with rasterio.open(temporary, "w", **profile) as output:
            output.write(data, 1)
            output.scales = ahn.scales
            output.offsets = ahn.offsets
            output.update_tags(**conversion)
            build_raster_overviews(
                output, factors=config.overview_factors, resampling=Resampling.average
            )
        with rasterio.open(temporary) as check:
            if not np.array_equal(check.read(1), data, equal_nan=True):
                raise ValueError(
                    f"RD/NAP-tegel is niet correct geschreven: {target_path}"
                )
        temporary.replace(target_path)
    finally:
        temporary.unlink(missing_ok=True)
    return target_path


def _convert_dgm1(
    source_path: Path,
    target_path: Path,
    ahn: rasterio.io.DatasetReader,
    transformer: Transformer,
) -> Path:
    """Convert one tile; reuse only an unchanged source and conversion."""
    conversion = {
        "source_version": str(_file_version(source_path)),
        "coordinate_operation": transformer.definition,
        "vertical_datum": "NAP",
        "conversion_version": "dgm1_rdnap_v1",
    }
    if _reuse_converted_tile(target_path, ahn, conversion):
        return target_path

    logger.info("DGM1 omzetten naar RD/NAP: %s", source_path.name)
    with rasterio.open(source_path) as source:
        if (
            not same_crs(source.crs, "EPSG:25832")
            or source.count != 1
            or source.scales != (1.0,)
            or source.offsets != (0.0,)
        ):
            raise ValueError(
                f"DGM1 moet UTM32 met hoogten in meters zijn: {source_path}"
            )
        # Controleer alle geldige cellen: buiten een correctiegrid niet doorgaan.
        values = source.read(1, masked=True)
        valid = ~np.ma.getmaskarray(values) & np.isfinite(values.data)
        rows, columns = np.nonzero(valid)
        x, y = rasterio.transform.xy(source.transform, rows, columns)
        transformer.transform(x, y, values.data[valid], errcheck=True)

    # Een samengesteld CRS laat GDAL ook de rasterhoogten transformeren.
    with gdal.Warp(
        "",
        source_path.as_posix(),
        format="MEM",
        srcSRS="EPSG:25832+7837",
        dstSRS="EPSG:7415",
        coordinateOperation=transformer.definition,
        xRes=1,
        yRes=1,
        targetAlignedPixels=True,
        resampleAlg="bilinear",
        outputType=gdal.GDT_Float64,
        dstNodata=float("nan"),
        errorThreshold=0,
    ) as warped:
        elevations = warped.ReadAsArray()
        left, resolution, _, top, _, _ = warped.GetGeoTransform()
        bounds = (
            left,
            top - warped.RasterYSize * resolution,
            left + warped.RasterXSize * resolution,
            top,
        )

    if not np.isfinite(elevations).any():
        raise ValueError(f"Geen geldige RD/NAP-hoogten na omzetting: {source_path}")
    # Dezelfde opslag als AHN: bijvoorbeeld centimeters bij schaal 0.01.
    stored = (elevations - ahn.offsets[0]) / ahn.scales[0]
    data = _cast_dem_data(stored, dtype=ahn.dtypes[0], nodata=ahn.nodata)
    if np.any(np.isfinite(elevations) & (data == ahn.nodata)):
        raise ValueError("Omgerekende hoogte valt samen met de AHN NoData-waarde")
    grid = RasterGrid.from_bounds(bounds, resolution=1, crs=str(ahn.crs))
    return _write_converted_tile(target_path, data, grid, ahn, conversion)


def prepare_ahn_dgm1_dem(
    ahn_vrt_path: Path,
    dgm1_dir: Path,
    *,
    converted_dir: Path,
    grid_dir: Path,
    output_path: Path,
) -> Path:
    """Maak een vlak AHN/DGM1-mozaïek in RD met NAP-hoogten.

    Parameters
    ----------
    ahn_vrt_path : pathlib.Path
        Bestaande vlakke AHN-VRT in RD/NAP. Geldig AHN heeft altijd voorrang.
    dgm1_dir : pathlib.Path
        Lokale originele NRW-GeoTIFFs in EPSG:25832 met DHHN2016-hoogten.
    converted_dir : pathlib.Path
        Cache voor 1m-tegels in RD/NAP, met dezelfde hoogteopslag als AHN.
        Ongewijzigde tegels worden hergebruikt, afwijkende caches geven een fout.
    grid_dir : pathlib.Path
        Lokale BKG/NSGI-correctiegrids; ontbrekende grids worden gedownload.
    output_path : pathlib.Path
        Nieuw VRT-bestand. Bestaande bestanden worden niet vervangen.

    Returns
    -------
    pathlib.Path
        DEM voor de bestaande tegelberekening, inclusief rekenbuffers.
        NoData wordt hier niet geïnterpoleerd. Brongegevens blijven ongewijzigd.
    """
    if output_path.exists():
        raise FileExistsError(output_path)
    source_paths = sorted(dgm1_dir.glob("dgm1_*.tif"))
    if not source_paths:
        raise FileNotFoundError(f"Geen DGM1-tegels gevonden in {dgm1_dir}")
    converted_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    transformer = _rdnap_transformer(grid_dir)
    with rasterio.open(ahn_vrt_path) as ahn:
        if (
            not same_crs(ahn.crs, "EPSG:28992")
            or ahn.count != 1
            or not np.isfinite(ahn.scales[0])
            or ahn.scales[0] <= 0
        ):
            raise ValueError("AHN moet RD/NAP gebruiken met een positieve hoogteschaal")
        converted = [
            _convert_dgm1(path, converted_dir / path.name, ahn, transformer)
            for path in source_paths
        ]
        ahn_sources = _vrt_sources(ahn_vrt_path.resolve(), _file_version(ahn_vrt_path))
        # Laatste bron heeft voorrang; AHN NoData laat DGM1 eronder door.
        sources = [*converted, *ahn_sources]
        temporary = _temporary_raster_path(output_path)
        try:
            with gdal.BuildVRT(
                temporary.as_posix(),
                [path.resolve().as_posix() for path in sources],
                options=gdal.BuildVRTOptions(
                    resolution="user",
                    xRes=ahn.res[0],
                    yRes=ahn.res[1],
                    targetAlignedPixels=True,
                    strict=True,
                ),
            ) as mosaic:
                band = mosaic.GetRasterBand(1)
                band.SetScale(ahn.scales[0])
                band.SetOffset(ahn.offsets[0])
                mosaic.SetMetadataItem("vertical_datum", "NAP")
            with rasterio.open(temporary) as check:
                if not same_crs(check.crs, ahn.crs) or check.scales != ahn.scales:
                    raise ValueError("Onverwachte CRS of hoogteschaal in DEM-mozaïek")
            temporary.replace(output_path)
        finally:
            temporary.unlink(missing_ok=True)
    logger.info("AHN + DGM1 in RD/NAP beschikbaar: %s", output_path)
    return output_path
