"""Download original NRW DGM1 tiles selected by area or tile ID."""

import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

import geopandas as gpd
import rasterio
import requests
from osgeo import gdal
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry

from waterlagen import datastore, settings
from waterlagen._crs import same_crs
from waterlagen._downloads import _temporary_path, stream_download_to_temp
from waterlagen.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.opengeodata.nrw.de/produkte/geobasis/hm/dgm1_tiff/dgm1_tiff/"
TILE_NAME = re.compile(
    r"dgm1_32_(?P<east>\d{3})_(?P<north>\d{4})_1_nw_(?P<year>\d{4})\.tif"
)


@dataclass(frozen=True)
class _Dgm1Tile:
    tile_id: str
    filename: str
    year: int
    geometry: Polygon


def _read_tile_index(timeout: float) -> list[_Dgm1Tile]:
    """Read the latest listed version of each 1 km UTM32 tile."""
    logger.info("Reading DGM1 tile index from %s", BASE_URL)
    with requests.get(BASE_URL, timeout=timeout) as response:
        response.raise_for_status()
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise ValueError("Invalid XML in NRW DGM1 tile index") from exc
    if root.tag != "opengeodata":
        raise ValueError("Unexpected NRW DGM1 tile index")

    tiles: dict[str, _Dgm1Tile] = {}
    for element in root.findall("./datasets/dataset/files/file"):
        filename = element.get("name", "")
        match = TILE_NAME.fullmatch(filename)
        if match is None:
            continue
        east = int(match["east"])
        north = int(match["north"])
        year = int(match["year"])
        tile_id = f"32_{east}_{north}"
        previous = tiles.get(tile_id)
        if previous is not None and previous.year >= year:
            continue
        xmin = east * 1000
        ymin = north * 1000
        tiles[tile_id] = _Dgm1Tile(
            tile_id=tile_id,
            filename=filename,
            year=year,
            geometry=box(xmin, ymin, xmin + 1000, ymin + 1000),
        )
    if not tiles:
        raise ValueError("NRW DGM1 tile index contains no supported tiles")
    return [tiles[tile_id] for tile_id in sorted(tiles)]


def get_tiles_features(
    poly_mask: BaseGeometry | None = None,
    select_indices: list[str] | None = None,
    *,
    timeout: float = 60,
) -> gpd.GeoDataFrame:
    """Select tiles from the current NRW file index.

    Parameters
    ----------
    poly_mask : shapely.geometry.base.BaseGeometry, optional
        Polygon or multipolygon in settings.crs. Intersecting tiles are selected.
    select_indices : list[str], optional
        Tile IDs such as "32_288_5736". Applied after the spatial selection.
    timeout : float, optional
        HTTP timeout in seconds, by default 60.

    Returns
    -------
    geopandas.GeoDataFrame
        Tile index in settings.crs, indexed by tile_id, with filename, url,
        year and geometry. The latest listed year is used for each tile.
        Without a selection, returns the complete index without downloading DEMs.
    """
    if not isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and greater than zero")
    if isinstance(select_indices, (str, bytes)):
        raise TypeError("select_indices must be a list of tile IDs, not a string")
    if poly_mask is not None:
        if poly_mask.is_empty or poly_mask.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("poly_mask must be a non-empty polygon or multipolygon")
        mask_utm = gpd.GeoSeries([poly_mask], crs=settings.crs).to_crs(25832).iloc[0]
    else:
        mask_utm = None
    selected = _read_tile_index(timeout)
    if mask_utm is not None:
        selected = [tile for tile in selected if tile.geometry.intersects(mask_utm)]
    tiles = (
        gpd.GeoDataFrame(
            {
                "tile_id": [tile.tile_id for tile in selected],
                "filename": [tile.filename for tile in selected],
                "year": [tile.year for tile in selected],
                "url": [BASE_URL + tile.filename for tile in selected],
            },
            geometry=[tile.geometry for tile in selected],
            crs=25832,
        )
        .set_index("tile_id")
        .to_crs(settings.crs)
    )
    if select_indices is not None:
        missing = set(select_indices) - set(tiles.index)
        if missing:
            raise ValueError(f"Unknown or unselected DGM1 tile IDs: {sorted(missing)}")
        tiles = tiles.loc[list(dict.fromkeys(select_indices))]
    return tiles


def _read_urls(path: Path) -> list[str]:
    """Read unique DGM1 URLs; reject unexpected hosts and file names."""
    if not path.is_file():
        raise FileNotFoundError(f"Downloadlijst ontbreekt: {path}")
    urls = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        filename = url.removeprefix(BASE_URL)
        if not url.startswith(BASE_URL) or not TILE_NAME.fullmatch(filename):
            raise ValueError(f"Geen geldige NRW DGM1-downloadlink: {url}")
        if url not in urls:
            urls.append(url)
    if not urls:
        raise ValueError(f"Downloadlijst is leeg: {path}")
    return urls


def _validate_geotiff(path: Path) -> None:
    """Check the original 1 km DGM1 grid and read every block for corruption."""
    with rasterio.open(path) as raster:
        if (
            raster.driver != "GTiff"
            or not same_crs(raster.crs, "EPSG:25832")
            or raster.count != 1
            or raster.shape != (1000, 1000)
            or raster.res != (1, 1)
        ):
            raise ValueError(f"Onverwacht DGM1-raster: {path}")
        for _, window in raster.block_windows(1):
            raster.read(1, window=window)


def _download_tile(
    url: str,
    output_dir: Path,
    *,
    missing_only: bool = True,
    retries: int = 3,
    timeout: float = 60,
) -> Path:
    """Reuse valid files; replace invalid files only after a validated download."""
    target = output_dir / url.rsplit("/", 1)[-1]
    if missing_only and target.is_file():
        try:
            _validate_geotiff(target)
        except (OSError, ValueError, rasterio.errors.RasterioError) as exc:
            logger.warning("Opnieuw downloaden van %s: %s", target.name, exc)
        else:
            logger.info("Hergebruik %s", target.name)
            return target

    for attempt in range(1, retries + 1):
        temporary_path = None
        try:
            download = stream_download_to_temp(
                url,
                target,
                timeout=timeout,
                logger=logger,
                progress=False,
            )
            temporary_path = download.target_path
            if (
                download.total_bytes is not None
                and download.downloaded_bytes != download.total_bytes
            ):
                raise ValueError(f"Onvolledige download: {target.name}")
            _validate_geotiff(temporary_path)
            temporary_path.replace(target)
            return target
        except Exception as exc:
            if attempt == retries:
                raise RuntimeError(
                    f"Download mislukt na {retries} pogingen: {target.name}"
                ) from exc
            logger.warning(
                "Poging %s/%s mislukt voor %s: %s", attempt, retries, target.name, exc
            )
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        time.sleep(2 * attempt)
    raise RuntimeError(f"Geen downloadpoging uitgevoerd voor {target.name}")


def _create_vrt(paths: list[Path], target: Path) -> Path:
    """Publish a VRT of the selected tiles only after checking its metadata."""
    logger.info("Creating DGM1 VRT %s from %s tiles", target, len(paths))
    temporary = _temporary_path(target, suffix=".vrt")
    mosaic = None
    try:
        mosaic = gdal.BuildVRT(
            str(temporary),
            [path.resolve().as_posix() for path in paths],
            options=gdal.BuildVRTOptions(strict=True),
        )
        if mosaic is None:
            raise ValueError("GDAL could not build the DGM1 VRT")
        mosaic.FlushCache()
        mosaic = None
        with rasterio.open(temporary) as check:
            if check.count != 1 or not same_crs(check.crs, "EPSG:25832"):
                raise ValueError("Unexpected CRS or band count in DGM1 VRT")
        temporary.replace(target)
    finally:
        mosaic = None
        temporary.unlink(missing_ok=True)
    return target


def download_dgm1(
    dgm1_dir: Path | None = None,
    poly_mask: BaseGeometry | None = None,
    select_indices: list[str] | None = None,
    missing_only: bool = True,
    create_vrt: bool = True,
    *,
    url_list: Path | None = None,
    workers: int = 4,
    retries: int = 3,
    timeout: float = 60,
) -> Path:
    """Download original DGM1 tiles with validated, atomic replacement.

    Parameters
    ----------
    dgm1_dir : pathlib.Path, optional
        Output directory. Defaults to datastore.dgm1_dir.
    poly_mask : shapely.geometry.base.BaseGeometry, optional
        Selection polygon in settings.crs, including any required buffer.
    select_indices : list[str], optional
        Tile IDs such as "32_288_5736". Combined with poly_mask when provided.
    missing_only : bool, optional
        Reuse valid local tiles, by default True. Invalid tiles are replaced
        only after a successful download. False downloads selected tiles again.
    create_vrt : bool, optional
        Create dgm1_nrw.vrt for the selected tiles, by default True.
        An existing VRT is replaced after all selected downloads succeed.
    url_list : pathlib.Path, optional
        Local list of NRW download URLs, instead of an online spatial selection.
        Cannot be combined with poly_mask or select_indices.
    workers : int, optional
        Number of download threads, by default 4.
    retries : int, optional
        Maximum total attempts per tile, by default 3.
    timeout : float, optional
        HTTP timeout in seconds, by default 60.

    Returns
    -------
    pathlib.Path
        VRT path, or the download directory when create_vrt=False.

    Notes
    -----
    Supply poly_mask, select_indices or url_list; an unbounded download is
    rejected. Original tiles retain UTM32 coordinates and DHHN2016 heights.
    No interpolation, height conversion or removal of older files is performed.
    """
    for name, value in (("workers", workers), ("retries", retries)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if not isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and greater than zero")
    if url_list is not None:
        if poly_mask is not None or select_indices is not None:
            raise ValueError(
                "url_list cannot be combined with a spatial or tile selection"
            )
        urls = _read_urls(Path(url_list))
    else:
        if poly_mask is None and select_indices is None:
            raise ValueError("Supply poly_mask, select_indices or url_list")
        tiles = get_tiles_features(poly_mask, select_indices, timeout=timeout)
        urls = tiles.url.tolist()
    if not urls:
        raise ValueError("No DGM1 tiles intersect the selection")
    output_dir = Path(dgm1_dir) if dgm1_dir is not None else datastore.dgm1_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Downloading %s DGM1 tiles with %s threads to %s",
        len(urls),
        workers,
        output_dir,
    )
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _download_tile,
                url,
                output_dir,
                missing_only=missing_only,
                retries=retries,
                timeout=timeout,
            ): url
            for url in urls
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            url = futures[future]
            try:
                path = future.result()
                logger.info("Completed %s/%s: %s", completed, len(urls), path.name)
            except Exception:
                failures.append(url)
                logger.exception("Failed %s/%s: %s", completed, len(urls), url)
    if failures:
        raise RuntimeError(
            f"DGM1 download failed for {len(failures)} tile(s): " + ", ".join(failures)
        )
    paths = [output_dir / url.rsplit("/", 1)[-1] for url in urls]
    logger.info("All %s DGM1 tiles available in %s", len(paths), output_dir)
    if create_vrt:
        return _create_vrt(paths, output_dir / "dgm1_nrw.vrt")
    return output_dir
