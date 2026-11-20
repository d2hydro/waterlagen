"""Discover and validate area-specific functional-land-use prerequisites."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import geopandas as gpd
import pyogrio
import rasterio

from waterlagen._crs import same_crs
from waterlagen._production import ProductionRun, default_run_id
from waterlagen._run_lock import run_is_locked
from waterlagen._sources import SourcePreparation
from waterlagen.areas import Area, ProductionArea, select_area_tiles
from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik import productie as landuse_production
from waterlagen.functioneel_landgebruik.gebouwen import (
    building_paths,
    validate_buildings,
)
from waterlagen.functioneel_landgebruik.paths import source_path
from waterlagen.logger import get_logger
from waterlagen.raster.tiles import read_tiles, tile_filename, tile_from_row
from waterlagen.settings import settings

logger = get_logger(__name__)


@dataclass(frozen=True)
class LanduseInput:
    """A validated production and its selected tile cores."""

    path: Path
    tiles: gpd.GeoDataFrame
    paths: list[Path]
    resolution_m: float


def _creation_time(metadata: dict) -> datetime:
    try:
        created = datetime.fromisoformat(metadata["created"])
        if created.tzinfo is None:
            raise ValueError("Creation time must include a timezone")
        return created
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Land-use metadata has no valid creation time") from error


def latest_run(directory: Path) -> Path | None:
    """Prefer the newest completed, unlocked run; otherwise check the latest."""
    candidates = []
    completed = []
    if not directory.exists():
        return None
    for path in directory.iterdir():
        if not path.is_dir() or not (path / "run.json").is_file():
            continue
        try:
            metadata = json.loads((path / "run.json").read_text(encoding="utf-8"))
            created = _creation_time(metadata)
        except (ValueError, KeyError, TypeError) as error:
            # Treat unrankable metadata as invalid, never silently use an older run.
            logger.warning("Invalid land-use metadata in %s: %s", path, error)
            return path
        candidate = (created, path.name, path)
        candidates.append(candidate)
        if metadata.get("status") == "complete" and not run_is_locked(path):
            completed.append(candidate)
    if completed:
        selected = max(completed)[2]
        if selected != max(candidates)[2]:
            logger.info(
                "Nieuwere landgebruikrun is onvoltooid of vergrendeld; afgeronde run kiezen: %s",
                selected,
            )
        return selected
    return max(candidates)[2] if candidates else None


class LanduseRunBusy(RuntimeError):
    """De geselecteerde landgebruikrun is bezig of vergrendeld."""


def _blocked_landuse(path: Path, reason: str) -> RuntimeError:
    """Een oude vergrendeling bewijst niet dat de productie nog draait."""
    return LanduseRunBusy(
        f"Landgebruikrun '{path.name}' {reason}.\n"
        "Deze run kan nog draaien of eerder zijn afgebroken.\n"
        "Controleer de productie, of kies een afgeronde run met --landuse-run.\n"
        f"Map: {path.resolve()}"
    )


def validate_landuse_run(
    path: Path, area: Area | ProductionArea, context_m: float
) -> LanduseInput:
    """Validate completed artifacts, including exact source-10 building cells.

    Parameters
    ----------
    path : pathlib.Path
        Functional-land-use production directory.
    area : Area
        Requested DEM area; a national production can supply Alkmaar.
    context_m : float
        Required building neighbour search distance in metres.

    Returns
    -------
    LanduseInput
        Selected cores on the production's original grid.
    """
    if run_is_locked(path):
        raise _blocked_landuse(path, "is vergrendeld")
    metadata = json.loads((path / "run.json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        # Invalid file content, rather than an incorrectly typed API argument.
        raise ValueError(f"Invalid land-use run metadata: {path}")  # noqa: TRY004
    if metadata.get("status") == "running":
        raise ValueError(
            f"Landgebruikrun '{path.name}' is onvoltooid. "
            f"Hervat deze run of kies een afgeronde landgebruikrun. Map: {path.resolve()}"
        )
    _creation_time(metadata)
    scopes = {area.value, Area.nederland.value}
    if (
        metadata.get("dataset") != "functioneel_landgebruik"
        or (
            not isinstance(area, ProductionArea) and metadata.get("scope") not in scopes
        )
        or metadata.get("status") != "complete"
    ):
        raise ValueError(f"No completed compatible land-use production: {path}")
    parameters = metadata["parameters"]
    mapping = path / "landgebruik_met_code.csv"
    if hashlib.sha256(mapping.read_bytes()).hexdigest() != parameters["csv_sha256"]:
        raise ValueError(f"Land-use classification CSV changed: {mapping}")
    tiles = read_tiles(path / "tiles.gpkg")
    if not same_crs(tiles.crs, settings.crs):
        raise ValueError("Land-use tile index CRS differs from project CRS")
    if isinstance(area, ProductionArea):
        grid = read_tiles(path / "grid.gpkg")
        expected = select_area_tiles(grid, area)
        if not set(expected.tile_id).issubset(set(tiles.tile_id)):
            raise ValueError("Land-use run does not cover every required tile")
    elif (path / "grid.gpkg").exists():
        expected = select_area_tiles(
            read_tiles(path / "grid.gpkg"), Area(metadata["scope"])
        )
        if set(expected.tile_id) != set(tiles.tile_id):
            raise ValueError("Land-use tile index is incomplete")
    selected = select_area_tiles(tiles, area)
    resolution = float(parameters["resolution_m"])
    paths = []
    for _, row in selected.iterrows():
        tile = tile_from_row(row)
        target = path / "tiles" / tile_filename("functioneel_landgebruik", tile)
        nested = path / "tiles" / tile.tile_id / "functioneel_landgebruik.tif"
        if parameters.get("tile_layout_version") == 2 or nested.is_file():
            target = nested
        for required in (target, source_path(target)):
            if not required.is_file():
                raise FileNotFoundError(required)
        validate_buildings(target, context_m)
        geometry_info = pyogrio.read_info(building_paths(target)[1], layer="gebouwen")
        if not same_crs(geometry_info["crs"], settings.crs) or not {
            "gebouw_id",
            "identificatie",
        }.issubset(geometry_info["fields"]):
            raise ValueError(
                f"Building geometry CRS or identity schema differs: {target}"
            )
        with rasterio.open(target) as source:
            if (
                tuple(source.bounds) != tile.bounds
                or source.res != (resolution, resolution)
                or not same_crs(source.crs, settings.crs)
                or source.transform.b
                or source.transform.d
                or source.transform.a <= 0
                or source.transform.e >= 0
            ):
                raise ValueError(f"Land-use tile grid differs from index: {target}")
        paths.append(target)
    return LanduseInput(path, selected, paths, resolution)


def find_landuse_input(
    store: DataStore, area: Area | ProductionArea, context_m: float
) -> LanduseInput | None:
    """Zoek geschikte lokale invoer zonder een productie te starten."""
    root = store.processed_data_dir / "functioneel_landgebruik"
    directories = sorted(root.iterdir()) if root.exists() else []
    directories.sort(key=lambda path: path.name != area.value)
    for directory in directories:
        candidate = latest_run(directory)
        if candidate is None:
            continue
        logger.info("Checking land-use production %s", candidate)
        try:
            return validate_landuse_run(candidate, area, context_m)
        except LanduseRunBusy:
            if directory.name == area.value:
                raise
            logger.info("Landgebruikrun uit ander gebied is bezig of vergrendeld, overslaan: %s", candidate)
            continue
        except (ValueError, KeyError, FileNotFoundError) as error:
            logger.info("Land-use production cannot supply DEM: %s", error)
            continue
    return None


def resolve_landuse(
    store: DataStore,
    run: ProductionRun,
    area: Area | ProductionArea,
    context_m: float,
    explicit: Path | None = None,
    *,
    preparation: SourcePreparation | None = None,
) -> LanduseInput:
    """Pin a valid input, or checkpoint and produce the requested area.

    Recorded dependencies are reused on resume. Automatic production calls the
    same function as the land-use CLI and never overwrites another production.
    """
    dependency = run.metadata.get("landuse_dependency")
    if dependency is not None:
        path = Path(dependency["path"])
        if dependency["created_by_dem"]:
            metadata_path = path / "run.json"
            metadata = (
                json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
            )
            if metadata.get("status") != "complete":
                if run_is_locked(path):
                    raise _blocked_landuse(path, "is vergrendeld")
                landuse_production.main(
                    store,
                    area=area,
                    run_id=path.name,
                    building_context_m=context_m,
                    resume=metadata_path.exists(),
                    preparation=preparation,
                )
        return validate_landuse_run(path, area, context_m)

    if explicit is not None:
        result = validate_landuse_run(explicit, area, context_m)
    else:
        result = None
        if preparation is None or not preparation.refresh:
            result = find_landuse_input(store, area, context_m)
    if result is not None:
        run.metadata["landuse_dependency"] = {
            "path": str(result.path.resolve()),
            "created_by_dem": False,
        }
        run._save()
        return result

    dependency_id = f"{default_run_id()}_{uuid4().hex[:8]}"
    path = (
        store.processed_data_dir
        / "functioneel_landgebruik"
        / area.value
        / dependency_id
    )
    run.metadata["landuse_dependency"] = {
        "path": str(path.resolve()),
        "created_by_dem": True,
    }
    run._save()  # Persist before starting expensive work, including failures.
    logger.info("Producing land-use prerequisite for %s in %s", area.value, path)
    landuse_production.main(
        store,
        area=area,
        run_id=dependency_id,
        building_context_m=context_m,
        preparation=preparation,
    )
    return validate_landuse_run(path, area, context_m)
