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
from waterlagen.areas import Area, select_area_tiles
from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik import productie as landuse_production
from waterlagen.functioneel_landgebruik.gebouwen import (
    building_paths,
    validate_buildings,
)
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
    """Find the newest recorded creation time, including unfinished runs."""
    candidates = []
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
        candidates.append((created, path.name, path))
    return max(candidates)[2] if candidates else None


def validate_landuse_run(path: Path, area: Area, context_m: float) -> LanduseInput:
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
    if (path / ".run.lock").exists():
        raise RuntimeError(f"Land-use production is running: {path}")
    metadata = json.loads((path / "run.json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        # Invalid file content, rather than an incorrectly typed API argument.
        raise ValueError(f"Invalid land-use run metadata: {path}")  # noqa: TRY004
    if metadata.get("status") == "running":
        raise RuntimeError(f"Land-use production is running: {path}")
    _creation_time(metadata)
    scopes = {area.value, Area.nederland.value}
    if (
        metadata.get("dataset") != "functioneel_landgebruik"
        or metadata.get("scope") not in scopes
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
    if (path / "grid.gpkg").exists():
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
        for required in (target, target.parent / "bronnen" / target.name):
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


def resolve_landuse(
    store: DataStore,
    run: ProductionRun,
    area: Area,
    context_m: float,
    explicit: Path | None = None,
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
                if (path / ".run.lock").exists():
                    raise RuntimeError(f"Land-use production is running: {path}")
                landuse_production.main(
                    store,
                    area=area,
                    run_id=path.name,
                    building_context_m=context_m,
                    resume=metadata_path.exists(),
                )
        return validate_landuse_run(path, area, context_m)

    if explicit is not None:
        result = validate_landuse_run(explicit, area, context_m)
    else:
        result = None
        scopes = [area] if area == Area.nederland else [Area.alkmaar, Area.nederland]
        for scope in scopes:
            candidate = latest_run(
                store.processed_data_dir / "functioneel_landgebruik" / scope.value
            )
            if candidate is None:
                continue
            logger.info("Checking land-use production %s", candidate)
            try:
                result = validate_landuse_run(candidate, area, context_m)
            except (ValueError, KeyError, FileNotFoundError) as error:
                logger.info("Land-use production cannot supply DEM: %s", error)
                continue
            break
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
        store, area=area, run_id=dependency_id, building_context_m=context_m
    )
    return validate_landuse_run(path, area, context_m)
