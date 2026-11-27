"""Prepare a reusable AHN tile cache and a production-specific VRT."""

from concurrent.futures import ThreadPoolExecutor
from math import isclose
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

import geopandas as gpd
import rasterio
from osgeo import gdal

from shapely.geometry.base import BaseGeometry

from waterlagen._crs import same_crs
from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._geopandas import read_file
from waterlagen._sources import SourcePreparation, prepare_cached
from waterlagen.ahn import AHNService, dekking, download_ahn, get_tiles_features
from waterlagen.ahn.api_config import AHN6_DTM_URL
from waterlagen.ahn.storage import download_target, reachable_source
from waterlagen.ahn.download import _is_valid_ahn_tile
from waterlagen.datastore import DataStore
from waterlagen.raster.vrt import create_cog_file, create_vrt_file
from waterlagen.settings import settings


AHNVersion = Literal[4, 5, 6]
LATEST_AHN: tuple[AHNVersion, ...] = (6, 5, 4)


def _published_tiles(
    store: DataStore,
    geometry: BaseGeometry,
    preparation: SourcePreparation,
    version: AHNVersion,
    cache: Path,
) -> gpd.GeoDataFrame:
    """Select tile URLs for the area and resolve AHN6 against its publication list."""
    service = AHNService(service="ahn_pdok" if version == 4 else "ahn_nl")
    index_path = cache / "ahn_dtm_05_index.gpkg"

    def download_index() -> None:
        cache.mkdir(parents=True, exist_ok=True)
        index = get_tiles_features(ahn_service=service, ahn_version=version)
        index["tile_id"] = index.index.astype(str)
        write_geopackage_layer_atomically(
            index.reset_index(drop=True), index_path, layer_name="tiles"
        )

    policy = preparation
    if version == 6 and not preparation.offline:
        policy = SourcePreparation(refresh=True, prepared=preparation.prepared)
    policy.ensure(index_path, download_index)
    index = read_file(index_path, layer="tiles").set_index("tile_id")
    if not same_crs(index.crs, settings.crs):
        index = index.to_crs(settings.crs)
    selected = index.loc[index.intersects(geometry)].copy()
    if version == 4 or selected.empty:
        return selected
    field = service.download_url_field(ahn_version=version)
    if version == 5:
        return selected.loc[selected[field].notna() & selected[field].ne("")]

    published = (
        dekking.publication(store.ahn_cache())
        if preparation.offline
        else dekking.refresh(store.ahn_cache(), lambda _: None)
    )
    markers = cache / "dtm_05"
    tiles = {}
    for sheet, planned_url in selected[field].items():
        has_url = isinstance(planned_url, str) and bool(planned_url)
        planned = Path(urlsplit(planned_url).path).stem if has_url else ""
        location = dekking.sheet_location(planned or str(sheet))
        name = published.by_location.get(location)
        if name:
            url = published.urls.get(name)
            if not url:
                # Older catalogues contain only filenames and use the AHN download directory.
                url = (
                    urljoin(planned_url, name + Path(urlsplit(planned_url).path).suffix)
                    if has_url
                    else AHN6_DTM_URL + name + ".TIF"
                )
        elif not planned:
            continue
        else:
            marker = markers / (planned + ".unpublished")
            if not preparation.offline:
                markers.mkdir(parents=True, exist_ok=True)
                marker.touch()
                continue
            if marker.exists():
                continue
            name, url = planned, planned_url
        tiles[sheet] = (name, url)
    selected = selected.loc[list(tiles)].copy()
    selected.index = [name for name, url in tiles.values()]
    selected[field] = [url for name, url in tiles.values()]
    return selected


def _prepare_version(
    store: DataStore,
    geometry: BaseGeometry,
    preparation: SourcePreparation,
    version: AHNVersion,
) -> list[Path]:
    """Reuse validated tiles and download missing ones to the chosen directory."""
    cache = store.ahn_cache()
    if version != 4:
        cache = cache / f"ahn{version}"
    selected = _published_tiles(store, geometry, preparation, version, cache)
    if selected.empty:
        return []

    directory = store.ahn_tiles(version)
    override = getattr(store, f"ahn{version}_data_dir")
    custom = bool(store.ahn_data_dir or override)
    if store.ahn_data_dir and store.ahn_data_dir.is_dir() and not override:
        try:
            directory.mkdir(exist_ok=True)
        except PermissionError:
            pass
    if custom and not directory.is_dir():
        directory = reachable_source(directory, version)

    paths = {}
    pending = []
    for name in selected.index:
        path = directory / f"{name}.tif"
        valid = _is_valid_ahn_tile(path)
        if not valid and store.ahn_download_dir:
            local = store.ahn_download_dir / f"AHN{version}" / path.name
            if local != path and _is_valid_ahn_tile(local):
                path, valid = local, True
        paths[name] = path
        if not valid or (
            preparation.refresh and path.resolve() not in preparation.prepared
        ):
            pending.append(name)

    if pending:
        if preparation.offline:
            raise FileNotFoundError(
                f"Geldige AHN-tegel ontbreekt in offline modus: {paths[pending[0]]}"
            )
        destination = (
            download_target(store, directory, version, len(pending))
            if custom
            else directory
        )
        for name in pending:
            paths[name] = destination / f"{name}.tif"

        def download_batch(names: list[str]) -> None:
            download_ahn(
                ahn_dir=cache,
                ahn_version=version,
                service="ahn_pdok" if version == 4 else "ahn_nl",
                tile_index=selected.loc[names],
                tile_directory=destination,
                missing_only=not preparation.refresh,
                create_vrt=False,
            )

        if version == 6 and len(pending) > 1:
            with ThreadPoolExecutor(max_workers=8) as pool:
                batches = [pending[start::8] for start in range(min(8, len(pending)))]
                list(pool.map(download_batch, batches))
        else:
            download_batch(pending)
    preparation.prepared.update(path.resolve() for path in paths.values())
    return list(paths.values())


def _mosaic(target: Path, sources: dict[Path, AHNVersion]) -> None:
    """Overlay aligned tiles from oldest to newest, retaining older heights beneath NoData."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp.vrt")
    if not sources:
        raise ValueError("AHN-mozaïek vereist bronbestanden")
    encoding = None
    for path in sources:
        with rasterio.open(path) as raster:
            transform = raster.transform
            rd_nap = (
                raster.crs is not None
                and raster.crs.to_epsg() == 7415
                and same_crs(settings.crs, "EPSG:28992")
            )
            if (
                not (rd_nap or same_crs(raster.crs, settings.crs))
                or raster.count != 1
                or (transform.a, transform.b, transform.d, transform.e)
                != (0.5, 0, 0, -0.5)
                or not isclose(
                    transform.c * 2, round(transform.c * 2), rel_tol=0, abs_tol=1e-7
                )
                or not isclose(
                    transform.f * 2, round(transform.f * 2), rel_tol=0, abs_tol=1e-7
                )
                or raster.nodata is None
            ):
                raise ValueError(
                    f"AHN-tegel is geen uitgelijnd 0,5 m-raster met NoData: {path}"
                )
            current = (raster.dtypes[0], raster.scales[0], raster.offsets[0])
            if encoding is not None and encoding != current:
                raise ValueError(
                    f"AHN-tegels gebruiken verschillende hoogteschalen: {path}"
                )
            encoding = current

    try:
        mosaic = gdal.BuildVRT(
            str(temporary),
            [str(path) for path in sources],
            options=gdal.BuildVRTOptions(
                strict=True,
                bandList=[1],
                allowProjectionDifference=True,
                outputSRS=settings.crs,
            ),
        )
        assert encoding is not None
        band = mosaic.GetRasterBand(1)
        band.SetScale(encoding[1])
        band.SetOffset(encoding[2])
        band.SetUnitType("m")
        band = None
        mosaic = None
        temporary.replace(target)

        # Use the same VRT sources and masks for the generation map. The
        # transform is applied only to valid source pixels by GDAL.
        tree = ET.parse(target)
        band_xml = tree.getroot().find("VRTRasterBand")
        band_xml.set("dataType", "Byte")
        for name in ("Scale", "Offset", "UnitType", "Metadata"):
            element = band_xml.find(name)
            if element is not None:
                band_xml.remove(element)
        band_xml.find("NoDataValue").text = "0"
        for source in band_xml.findall("ComplexSource") + band_xml.findall(
            "SimpleSource"
        ):
            filename = source.find("SourceFilename")
            path = (target.parent / filename.text).resolve()
            source.tag = "ComplexSource"
            ET.SubElement(source, "ScaleOffset").text = str(sources[path])
            ET.SubElement(source, "ScaleRatio").text = "0"
        tree.write(temporary, encoding="utf-8")
        temporary.replace(target.with_name("ahn_versie.vrt"))
    finally:
        temporary.unlink(missing_ok=True)


def prepare_ahn(
    store: DataStore,
    geometry: BaseGeometry,
    target_vrt: Path,
    preparation: SourcePreparation,
    *,
    versions: tuple[AHNVersion, ...] = (4,),
    include_version_raster: bool = False,
) -> Path:
    """Build the height mosaic from the newest valid cell; default to AHN4.

    Also write ahn_versie.vrt for multigeneration and AHN5/6 mosaics, or on request for AHN4."""
    sources = {
        path.resolve(): version
        for version in sorted(set(versions))
        for path in _prepare_version(store, geometry, preparation, version)
    }
    if not sources:
        raise ValueError("Geen gepubliceerde AHN-tegels in het benodigde rekengebied")
    if not include_version_raster and versions == (4,):
        return prepare_cached(
            target_vrt,
            {path.name: path for path in sources},
            lambda: create_vrt_file(target_vrt, files=list(sources)),
        )
    _mosaic(target_vrt, sources)
    return target_vrt


def export_ahn_versions(input_vrt: Path, tiles: list[Path], output: Path) -> Path:
    """Export the AHN generation over the same tile footprints as the DEM."""
    tile_dir = output / "input" / "ahn_versie"
    tile_dir.mkdir(parents=True, exist_ok=True)
    clipped = []
    for number, tile in enumerate(tiles):
        with rasterio.open(tile) as reference:
            left, bottom, right, top = reference.bounds
        target = tile_dir / f"{number}.vrt"
        dataset = gdal.Translate(
            str(target),
            str(input_vrt),
            format="VRT",
            projWin=(left, top, right, bottom),
        )
        dataset.FlushCache()
        dataset = None
        clipped.append(target)
    vrt = create_vrt_file(output / "ahn_versie.vrt", files=clipped)
    return create_cog_file(vrt, output / "ahn_versie.tif", overwrite=True)
