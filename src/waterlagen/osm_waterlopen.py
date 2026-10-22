"""Download open OSM canal lines for optional drainage burn layers."""

import json
from math import isfinite
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from pyproj import Transformer
from shapely.geometry import LineString, box

from waterlagen._crs import format_crs, same_crs
from waterlagen._downloads import _temporary_path, validate_geopackage
from waterlagen._filesystem import replace_file
from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._overpass import OVERPASS_ENDPOINT, _read_overpass
from waterlagen._production import _file_identity
from waterlagen.areas import area_from_bounds
from waterlagen.datastore import DataStore
from waterlagen.logger import get_logger
from waterlagen.settings import settings

logger = get_logger(__name__)
CANALS_LAYER = "osm_canals"


def _canal_lines(payload: dict, bounds: tuple[float, ...]) -> gpd.GeoDataFrame:
    """Reject incomplete ways and retain open canals intersecting the selection."""
    timestamp = payload.get("osm3s", {}).get("timestamp_osm_base")
    if not isinstance(timestamp, str) or not timestamp:
        raise ValueError("Overpass-antwoord mist de OSM-peildatum")
    rows = []
    seen = set()
    for element in payload["elements"]:
        tags = element.get("tags", {})
        identifier = element.get("id")
        if (
            element.get("type") != "way"
            or tags.get("waterway") != "canal"
            or not isinstance(identifier, int)
            or isinstance(identifier, bool)
            or identifier in seen
        ):
            raise ValueError(f"Ongeldig of dubbel OSM-kanaal: {identifier}")
        seen.add(identifier)
        if (
            tags.get("tunnel", "no") != "no"
            or tags.get("covered", "no") != "no"
            or tags.get("location") == "underground"
        ):
            continue
        try:
            coordinates = [
                (point["lon"], point["lat"]) for point in element["geometry"]
            ]
            if len(coordinates) < 2 or not all(
                isfinite(x) and isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90
                for x, y in coordinates
            ):
                raise ValueError("invalid coordinates")
            geometry = LineString(coordinates)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Onvolledige geometrie voor OSM-kanaal {identifier}"
            ) from error
        if geometry.is_empty or not geometry.is_valid or geometry.length == 0:
            raise ValueError(f"Ongeldige geometrie voor OSM-kanaal {identifier}")
        rows.append(
            {
                "osm_id": identifier,
                "naam": tags.get("name"),
                "waterway": "canal",
                "osm_tags": json.dumps(tags, ensure_ascii=False, sort_keys=True),
                "osm_peildatum_utc": timestamp,
                "bron": "OpenStreetMap contributors",
                "licentie": "ODbL",
                "geometry": geometry,
            }
        )
    if not rows:
        return gpd.GeoDataFrame(
            {
                "osm_id": pd.Series(dtype="int64"),
                **{
                    name: pd.Series(dtype="str")
                    for name in (
                        "naam",
                        "waterway",
                        "osm_tags",
                        "osm_peildatum_utc",
                        "bron",
                        "licentie",
                    )
                },
            },
            geometry=gpd.GeoSeries([], crs=settings.crs),
        )
    lines = gpd.GeoDataFrame(rows, crs="EPSG:4326").to_crs(settings.crs)
    return (
        lines.loc[lines.intersects(box(*bounds))]
        .sort_values("osm_id")
        .reset_index(drop=True)
    )


def download_osm_canals(
    bounds: tuple[float, float, float, float],
    target_path: Path | None = None,
    *,
    data_store: DataStore | None = None,
    overwrite: bool = False,
    endpoint: str = OVERPASS_ENDPOINT,
    timeout: float = 180,
) -> Path:
    """Download open canal ways to source_data/osm/osm_canals.gpkg.

    Parameters
    ----------
    bounds : tuple of float
        xmin, ymin, xmax, ymax in ``settings.crs``. Include calculation buffers.
        Intersecting ways are retained whole, not clipped to the bounds.
    target_path : pathlib.Path, optional
        Override the default GeoPackage path.
    data_store : DataStore, optional
        Configured source-data location.
    overwrite : bool, optional
        Replace an existing validated download. Otherwise reuse only when
        selection, endpoint, CRS and recorded output identity match. A different
        selection requires another target path or explicit overwrite.
    endpoint : str, optional
        Overpass interpreter URL.
    timeout : float, optional
        Positive HTTP timeout in seconds, default 180.

    Returns
    -------
    pathlib.Path
        GeoPackage with layer ``osm_canals`` in the project CRS. Empty selections
        produce a valid empty layer. A JSON sidecar records selection and source.

    Raises
    ------
    ValueError
        Invalid bounds, incomplete OSM data or incompatible existing download.
    RuntimeError
        Overpass request failed.
    """
    selection = area_from_bounds(bounds)
    bounds = selection.geometry.bounds
    if isinstance(timeout, bool) or not isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout moet positief en eindig zijn")
    store = data_store or DataStore()
    target = Path(target_path or store.source_data_dir / "osm" / "osm_canals.gpkg")
    west, south, east, north = Transformer.from_crs(
        settings.crs, "EPSG:4326", always_xy=True
    ).transform_bounds(*bounds, densify_pts=21)
    if not all(isfinite(value) for value in (west, south, east, north)):
        raise ValueError("Gebiedsgrenzen kunnen niet naar WGS84 worden getransformeerd")
    query = (
        f"[out:json][timeout:{max(1, int(timeout) - 10)}];"
        f'way["waterway"="canal"]({south},{west},{north},{east});out geom;'
    )
    identity = {
        "bounds": list(bounds),
        "crs": format_crs(settings.crs),
        "endpoint": endpoint,
        "policy": "open_canals_v1",
    }
    manifest = target.with_suffix(".json")
    if target.is_file() and not overwrite:
        validate_geopackage(target)
        info = pyogrio.read_info(target, layer=CANALS_LAYER)
        metadata = (
            json.loads(manifest.read_text(encoding="utf-8"))
            if manifest.exists()
            else {}
        )
        if (
            metadata.get("selection") != identity
            or metadata.get("output") != _file_identity(target)
            or info["crs"] is None
            or not same_crs(info["crs"], settings.crs)
        ):
            raise ValueError(
                "Bestaande OSM-kanalen hebben andere invoer; kies een ander pad of overwrite=True"
            )
        logger.info("OSM-kanalen hergebruiken: %s", target)
        return target
    payload = _read_overpass(
        query,
        "kanalen",
        endpoint=endpoint,
        cache_dir=None,
        offline=False,
        timeout=timeout,
    )
    lines = _canal_lines(payload, bounds)
    logger.info("OSM-kanalen schrijven: %s (%s lijnen)", target, len(lines))
    write_geopackage_layer_atomically(lines, target, layer_name=CANALS_LAYER)
    metadata = {
        "selection": identity,
        "query": query,
        "output": _file_identity(target),
        "osm_peildatum_utc": payload["osm3s"]["timestamp_osm_base"],
        "attribution": "© OpenStreetMap contributors, ODbL",
    }
    temporary = _temporary_path(manifest, suffix=".json")
    try:
        temporary.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        replace_file(temporary, manifest)
    finally:
        temporary.unlink(missing_ok=True)
    return target
