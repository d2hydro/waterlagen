"""Explicit public burn sources, with provenance and coverage-aware reuse."""

import json
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

import pyogrio
from pyproj import Transformer
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from waterlagen._crs import format_crs, same_crs
from waterlagen._downloads import _temporary_path, validate_geopackage
from waterlagen._filesystem import replace_file
from waterlagen._production import _file_identity
from waterlagen._sources import SourcePreparation
from waterlagen.bgt.download import (
    DEFAULT_PREDEFINED_ARCHIVE,
    _convert_bgt_zip_to_geopackage,
    _download_validated_zip_archive,
    poll_downloadstatus,
    request_download,
)
from waterlagen.bgt.duikers import prepare_bgt_culverts
from waterlagen.bgt.prepare import prepare_surface_layer
from waterlagen.datastore import DataStore
from waterlagen.logger import get_logger
from waterlagen.osm_waterlopen import (
    WATERWAY_LAYERS,
    download_osm_culverts,
    download_osm_waterlopen,
)
from waterlagen.settings import settings
from waterlagen.top10nl import download_top10nl
from waterlagen.top10nl.download import TOP10NL_FILENAME

from .config import Brandlaag, BrandlagenConfig

logger = get_logger(__name__)
POLICY = "public_brand_sources_v1"


@dataclass(frozen=True)
class PreparedBrandSources:
    """Resolved source paths and provenance files for the existing run metadata."""

    config: BrandlagenConfig
    inputs: dict[str, Path]


def _manifest(path: Path) -> Path:
    return path.with_suffix(".brandbron.json")


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _identity(path: Path) -> dict:
    return {
        "file": _file_identity(path),
        "wal": _file_identity(Path(str(path) + "-wal")),
    }


def _layer_exists(path: Path, layer: str) -> bool:
    try:
        info = pyogrio.read_info(path, layer=layer)
        return info["crs"] is not None
    except (OSError, ValueError, RuntimeError):
        return False


def _owned(path: Path, dataset: str) -> bool:
    meta = _read_json(_manifest(path))
    return bool(
        path.is_file()
        and meta.get("dataset") == dataset
        and meta.get("output") == _identity(path)
    )


def _matching_coverage(path: Path, dataset: str, bounds: tuple | None) -> bool:
    if not _owned(path, dataset):
        return False
    meta = _read_json(_manifest(path))
    if meta.get("policy") != POLICY:
        return False
    upstream_sources = meta.get("sources", {})
    if not isinstance(upstream_sources, dict):
        return False
    for name, identity in upstream_sources.items():
        upstream = Path(name)
        if upstream.exists() and _identity(upstream) != identity:
            return False
    if meta.get("coverage") == "national":
        return True
    if bounds is None:
        return False
    try:
        return same_crs(meta["crs"], settings.crs) and box(*meta["coverage"]).covers(
            box(*bounds)
        )
    except (KeyError, TypeError, ValueError):
        return False


def _reusable(path: Path, dataset: str, layer: str, bounds: tuple | None) -> bool:
    return _matching_coverage(path, dataset, bounds) and _layer_exists(path, layer)


def _save_manifest(
    path: Path, dataset: str, bounds: tuple | None, sources: tuple[Path, ...] = ()
) -> None:
    metadata = {
        "policy": POLICY,
        "dataset": dataset,
        "output": _identity(path),
        "coverage": list(bounds) if bounds is not None else "national",
        "crs": format_crs(settings.crs),
        "sources": {str(p.resolve()): _identity(p) for p in sources},
    }
    manifest = _manifest(path)
    temporary = _temporary_path(manifest, suffix=".json")
    try:
        temporary.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        replace_file(temporary, manifest)
    finally:
        temporary.unlink(missing_ok=True)


def _destination(requested: Path, fallback: Path, dataset: str) -> Path:
    if not requested.exists() or _owned(requested, dataset):
        return requested
    logger.info(
        "Herkomst niet aantoonbaar; behoud eigen bestand %s en gebruik broncache %s",
        requested,
        fallback,
    )
    if fallback.exists() and not _owned(fallback, dataset):
        raise ValueError(
            f"Broncache {fallback} is gewijzigd of heeft geen herkomstmetadata; kies een ander pad"
        )
    return fallback


def _require_preparation(
    path: Path, preparation: SourcePreparation, reuse_only: bool, *, download: bool
) -> None:
    if reuse_only:
        raise ValueError(
            f"Openbare brandbron ontbreekt of is gewijzigd: {path}. Kies een nieuwe --run-id."
        )
    if download and preparation.offline:
        raise FileNotFoundError(
            f"Openbare brandbron ontbreekt of heeft onvoldoende dekking: {path}; offline actief"
        )


def _archive(
    store: DataStore,
    preparation: SourcePreparation,
    feature_type: str,
    bounds: tuple,
) -> Path:
    # Keep proven national archives usable, but acquire missing data by area.
    for national in (
        store.bgt_dir / DEFAULT_PREDEFINED_ARCHIVE,
        store.bgt_dir / "brandlagen" / DEFAULT_PREDEFINED_ARCHIVE,
    ):
        if not preparation.refresh and _matching_coverage(
            national, "bgt_archive", None
        ):
            logger.info("Bestaande landelijke BGT-bron hergebruiken: %s", national)
            return national
    path = store.bgt_dir / "brandlagen" / "gebied" / f"bgt_{feature_type}.zip"
    dataset = f"bgt_{feature_type}_archive"
    refreshed = preparation.refresh and path not in preparation.prepared
    if not refreshed and _matching_coverage(path, dataset, bounds):
        logger.info("Gebiedsgerichte BGT-bron hergebruiken: %s", path)
        return path
    if path.exists() and not _owned(path, dataset):
        raise ValueError(
            f"Onbekend of gewijzigd bestand in beheerde BGT-broncache: {path}"
        )
    _require_preparation(path, preparation, False, download=True)
    # The existing custom API expects RD coordinates, regardless of project CRS.
    selection = box(*bounds)
    if not same_crs(settings.crs, "EPSG:28992"):
        transformer = Transformer.from_crs(settings.crs, "EPSG:28992", always_xy=True)
        selection = box(*transformer.transform_bounds(*bounds, densify_pts=101))
    logger.info(
        "BGT-%s ophalen voor rekengebied inclusief buffers %s", feature_type, bounds
    )
    request_id = request_download((feature_type,), selection)
    download_url = poll_downloadstatus(request_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    _download_validated_zip_archive(
        url=download_url,
        archive_path=path,
        description=f"BGT-{feature_type} voor rekengebied",
        chunk_size=1024 * 1024,
        timeout=300,
        progress=False,
    )
    _save_manifest(path, dataset, bounds)
    preparation.prepared.add(path)
    return path


def _prepared_source(
    layer: Brandlaag,
    store: DataStore,
    preparation: SourcePreparation,
    reuse_only: bool,
    bounds: tuple,
) -> Path:
    dataset = "top10nl" if layer.openbare_bron == "top10nl" else layer.layer
    fallback = (
        store.source_data_dir
        / "brandlagen"
        / dataset
        / (TOP10NL_FILENAME if dataset == "top10nl" else f"{dataset}.gpkg")
    )
    standard = (
        store.top10nl_dir / TOP10NL_FILENAME
        if dataset == "top10nl"
        else store.bgt_dir / "bgt.gpkg"
    )
    coverage = None if dataset == "top10nl" else bounds
    for candidate in dict.fromkeys((layer.path, standard, fallback)):
        refreshed = preparation.refresh and candidate not in preparation.prepared
        if not refreshed and _reusable(candidate, dataset, layer.layer, coverage):
            logger.info("Openbare brandbron hergebruiken: %s", candidate)
            return candidate
    target = _destination(layer.path, fallback, dataset)
    _require_preparation(target, preparation, reuse_only, download=dataset == "top10nl")
    target.parent.mkdir(parents=True, exist_ok=True)
    if dataset == "top10nl":
        logger.info("Landelijke TOP10NL-download nodig: %s", target)
        with tempfile.TemporaryDirectory(
            prefix=".top10nl_", dir=target.parent
        ) as folder:
            temporary = download_top10nl(download_dir=Path(folder), overwrite=True)
            if not _layer_exists(temporary, layer.layer):
                raise ValueError(f"TOP10NL bevat geen bruikbare laag {layer.layer}")
            replace_file(temporary, target)
        upstream = ()
    else:
        feature_type = layer.layer.removeprefix("bgt_")
        archive = _archive(store, preparation, feature_type, bounds)
        if _read_json(_manifest(archive)).get("coverage") == "national":
            coverage = None
        logger.info("BGT-laag %s voorbereiden uit %s", layer.layer, archive)
        with tempfile.TemporaryDirectory(
            prefix=f".{layer.layer}_", dir=target.parent
        ) as folder:
            temporary = prepare_surface_layer(archive, Path(folder), feature_type)
            if temporary is None:
                raise ValueError(f"BGT bevat geen actuele vlakken voor {layer.layer}")
            replace_file(temporary, target)
        upstream = (archive,)
    _save_manifest(target, dataset, coverage, upstream)
    preparation.prepared.add(target)
    return target


def _bgt_culverts(
    layer: Brandlaag,
    store: DataStore,
    selection: BaseGeometry,
    preparation: SourcePreparation,
    reuse_only: bool,
) -> Path:
    dataset = "bgt_duiker"
    fallback = store.processed_data_dir / "brandlagen" / "openbaar" / "bgt_duikers.gpkg"
    bounds = selection.bounds
    for candidate in dict.fromkeys((layer.path, fallback)):
        refreshed = preparation.refresh and candidate not in preparation.prepared
        if not refreshed and _reusable(candidate, dataset, layer.layer, bounds):
            logger.info("BGT-duikerselectie hergebruiken: %s", candidate)
            return candidate
    target = _destination(layer.path, fallback, dataset)
    _require_preparation(target, preparation, reuse_only, download=False)
    raw = store.bgt_dir / "brandlagen" / "bgt_kunstwerkdeel.gpkg"
    if raw.exists() and not _owned(raw, "bgt_kunstwerkdeel"):
        raise ValueError(
            f"Onbekend of gewijzigd bestand in beheerde BGT-broncache: {raw}"
        )
    refresh_raw = preparation.refresh and raw not in preparation.prepared
    if refresh_raw or not _reusable(
        raw, "bgt_kunstwerkdeel", "bgt_kunstwerkdeel", bounds
    ):
        archive = _archive(store, preparation, "kunstwerkdeel", bounds)
        if refresh_raw or not _reusable(
            raw, "bgt_kunstwerkdeel", "bgt_kunstwerkdeel", bounds
        ):
            raw.parent.mkdir(parents=True, exist_ok=True)
            logger.info(
                "BGT-kunstwerkdelen voorbereiden met behoud van lijnen en vlakken"
            )
            _convert_bgt_zip_to_geopackage(
                archive, raw, ["kunstwerkdeel"], expected_crs="EPSG:28992"
            )
            coverage = (
                None
                if _read_json(_manifest(archive)).get("coverage") == "national"
                else bounds
            )
            _save_manifest(raw, "bgt_kunstwerkdeel", coverage, (archive,))
        preparation.prepared.add(raw)
    else:
        archive = Path(next(iter(_read_json(_manifest(raw))["sources"])))
    prepare_bgt_culverts(raw, target, box(*bounds))
    _save_manifest(target, dataset, bounds, (raw, archive))
    preparation.prepared.add(target)
    return target


def _osm_reusable(path: Path, layer: str, bounds: tuple) -> bool:
    metadata = _read_json(path.with_suffix(".json"))
    selection = metadata.get("selection", {})
    if not isinstance(selection, dict):
        return False
    policy = (
        "culverts_v1"
        if layer == "osm_culvert"
        else f"open_{layer.removeprefix('osm_')}_v1"
    )
    try:
        return bool(
            path.is_file()
            and metadata.get("output") == _file_identity(path)
            and not Path(str(path) + "-wal").exists()
            and selection.get("policy") == policy
            and same_crs(selection["crs"], settings.crs)
            and box(*selection["bounds"]).covers(box(*bounds))
            and _layer_exists(path, layer)
        )
    except (KeyError, TypeError, ValueError):
        return False


def _osm(
    layer: Brandlaag,
    store: DataStore,
    bounds: tuple,
    preparation: SourcePreparation,
    reuse_only: bool,
) -> Path:
    standard = (
        store.source_data_dir
        / "osm"
        / (
            "osm_culverts.gpkg"
            if layer.layer == "osm_culvert"
            else f"{layer.layer}.gpkg"
        )
    )
    fallback = standard.parent / "brandlagen" / standard.name
    for candidate in dict.fromkeys((layer.path, standard, fallback)):
        refreshed = preparation.refresh and candidate not in preparation.prepared
        if not refreshed and _osm_reusable(candidate, layer.layer, bounds):
            logger.info(
                "OSM-brandbron hergebruiken, dekking inclusief buffers: %s", candidate
            )
            return candidate
    # Only replace an output whose native download metadata still matches.
    target = layer.path
    if target.exists():
        meta = _read_json(target.with_suffix(".json"))
        own_bounds = meta.get("selection", {}).get("bounds")
        if not own_bounds or not _osm_reusable(target, layer.layer, tuple(own_bounds)):
            target = fallback
    if target.exists():
        own_bounds = (
            _read_json(target.with_suffix(".json")).get("selection", {}).get("bounds")
        )
        if not own_bounds or not _osm_reusable(target, layer.layer, tuple(own_bounds)):
            raise ValueError(
                f"Bestaand OSM-bestand heeft geen geldige herkomstmetadata: {target}"
            )
    _require_preparation(target, preparation, reuse_only, download=True)
    logger.info(
        "OSM-brandbron ophalen voor rekengebied inclusief buffers %s: %s",
        bounds,
        layer.layer,
    )
    if layer.layer == "osm_culvert":
        download_osm_culverts(
            bounds, target_path=target, data_store=store, overwrite=True
        )
    else:
        waterway = next(
            key for key, name in WATERWAY_LAYERS.items() if name == layer.layer
        )
        download_osm_waterlopen(
            bounds,
            waterway=waterway,
            target_path=target,
            data_store=store,
            overwrite=True,
        )
    if not _osm_reusable(target, layer.layer, bounds):
        raise ValueError(
            f"OSM-download mist geldige laag of dekkingsmetadata: {target}"
        )
    preparation.prepared.add(target)
    return target


def prepare_brand_sources(
    config: BrandlagenConfig,
    store: DataStore,
    selection: BaseGeometry,
    preparation: SourcePreparation,
    *,
    reuse_only: bool = False,
) -> PreparedBrandSources:
    """Resolve only explicitly requested public layers before calculating a run.

    Local entries are never downloaded or replaced. Unverified existing public
    paths are left intact; a managed cache is used instead. Resume/overwrite
    only resolve existing compatible sources and never regenerate them.

    Parameters
    ----------
    config : BrandlagenConfig
        Requested layers, retaining local paths, defaults and object overrides.
    store : DataStore
        Shared source and preparation caches.
    selection : BaseGeometry
        Union of calculation tiles including buffers, in ``settings.crs``.
    preparation : SourcePreparation
        Offline and refresh policy. Refresh must not be combined with offline
        or reuse-only operation.
    reuse_only : bool, optional
        Require existing compatible sources for resume or overwrite.

    Returns
    -------
    PreparedBrandSources
        Resolved configuration and provenance files to record with the run.
    """
    if preparation.refresh and (preparation.offline or reuse_only):
        raise ValueError(
            "Bronnen vernieuwen vereist een nieuwe run zonder offline of hervatten"
        )
    for layer in config.lagen:
        if layer.openbare_bron is None and not layer.path.is_file():
            raise FileNotFoundError(
                f"Eigen lokale brandlaag ontbreekt: {layer.path} ({layer.layer}); geen download ingesteld"
            )
    layers = []
    inputs = {}
    resolved: dict[tuple[str, Path, str], Path] = {}
    for index, layer in enumerate(config.lagen):
        if layer.openbare_bron is None:
            layers.append(layer)
            continue
        key = (layer.openbare_bron, layer.path, layer.layer)
        if key in resolved:
            target = resolved[key]
        elif layer.openbare_bron == "osm":
            target = _osm(layer, store, selection.bounds, preparation, reuse_only)
        elif layer.layer == "bgt_duiker":
            target = _bgt_culverts(layer, store, selection, preparation, reuse_only)
        else:
            target = _prepared_source(
                layer, store, preparation, reuse_only, selection.bounds
            )
        resolved[key] = target
        validate_geopackage(target)
        layers.append(replace(layer, path=target))
        manifest = (
            target.with_suffix(".json")
            if layer.openbare_bron == "osm"
            else _manifest(target)
        )
        inputs[f"brandbron_{index}_metadata"] = manifest
    return PreparedBrandSources(replace(config, lagen=tuple(layers)), inputs)
