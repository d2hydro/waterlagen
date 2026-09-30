"""Download OSM drinking-water sites as reviewable polygons for BAG matching."""

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import pyogrio
import requests
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from waterlagen._crs import same_crs
from waterlagen._downloads import validate_geopackage
from waterlagen._geopackage import write_geopackage_layer
from waterlagen.datastore import DataStore
from waterlagen.logger import get_logger
from waterlagen.settings import settings

logger = get_logger(__name__)

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
DRINKWATER_LAYER = "drinkwaterproductieterrein"
SITE_LAYER = "terreinen_waterbedrijven"
BUILDING_LAYER = "gebouwcontouren"
REVIEWS_PATH = Path(__file__).with_name("drinkwater_beoordelingen.json")

# Deze twee locaties blijven buiten de selectie op verzoek van de gebruiker.
EXCLUDED_POLYGON_IDS = {
    "way/265176673": "Gebouw Amersfoort-Koedijkerweg",
    "way/1487136894": "Terrein Waterwinning Schiermonnikoog",
}

OsmElement = dict[str, Any]


@dataclass(frozen=True)
class ReviewedLocation:
    """One location from the supplied, dated source review."""

    name: str
    operator: str
    kind: str
    location_id: str
    polygon_id: str
    review_date: str


@dataclass(frozen=True)
class DrinkingWaterPolygon:
    """An OSM geometry selected for a drinking-water production location."""

    name: str
    operator: str
    kind: str
    location_id: str
    polygon_id: str
    review_date: str
    geometry: BaseGeometry


def _osm_id(element: OsmElement) -> str:
    return f"{element['type']}/{element['id']}"


def _validate_response(payload: object, description: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError(f"Overpass-{description} is geen JSON-object.")
    if payload.get("remark"):
        raise ValueError(f"Overpass-{description} is onvolledig: {payload['remark']}")
    if not isinstance(payload.get("elements"), list):
        raise TypeError(f"Overpass-{description} bevat geen elementenlijst.")
    return payload


def _read_overpass(
    query: str,
    description: str,
    *,
    endpoint: str,
    cache_dir: Path | None,
    offline: bool,
    timeout: float,
) -> dict[str, Any]:
    cache_path = cache_dir / f"{description}.json" if cache_dir else None
    if offline:
        if cache_path is None:
            raise ValueError("Offline gebruik vereist een cachemap.")
        logger.info("Hergebruik OSM-%s uit %s", description, cache_path)
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"OSM-cache ontbreekt of is ongeldig: {cache_path}"
            ) from exc
        return _validate_response(payload, description)

    logger.info("Ophalen OSM-%s via Overpass", description)
    for attempt in range(3):
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                headers={
                    "User-Agent": "waterlagen/OSM-drinkwater",
                    "Accept": "application/json",
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            break
        except (requests.RequestException, requests.exceptions.JSONDecodeError) as exc:
            retryable = isinstance(exc, requests.RequestException) and (
                not isinstance(exc, requests.HTTPError)
                or exc.response is not None
                and exc.response.status_code in {406, 429, 500, 502, 503, 504}
            )
            if not retryable or attempt == 2:
                raise RuntimeError(f"OSM-{description} ophalen mislukt: {exc}") from exc
            delay = 30 * (attempt + 1)
            logger.warning(
                "Overpass tijdelijk niet bereikbaar; opnieuw over %s s", delay
            )
            time.sleep(delay)
    result = _validate_response(payload, description)
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        temporary.replace(cache_path)
    return result


def _read_reviews(path: Path) -> list[ReviewedLocation]:
    """Select only confirmed treatment sites from the supplied source review."""
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Drinkwaterbeoordelingen ontbreken of zijn ongeldig: {path}"
        ) from exc
    if not isinstance(records, list):
        raise TypeError("Drinkwaterbeoordelingen moeten een lijst zijn.")

    selected = []
    seen = set()
    for record in records:
        if record["oordeel"] != "drinkwaterzuivering":
            continue
        polygon_id = record["osm_ids"]
        if polygon_id in EXCLUDED_POLYGON_IDS:
            logger.info("OSM-vlak uitgesloten: %s", polygon_id)
            continue
        if polygon_id in seen:
            raise ValueError(f"Dubbel beoordeeld OSM-vlak: {polygon_id}")
        if record["vlak_type"] not in {"gebouw", "terrein"}:
            raise ValueError(f"Onbekend drinkwatervlaktype: {polygon_id}")
        seen.add(polygon_id)
        selected.append(
            ReviewedLocation(
                name=record["naam"],
                operator=record["exploitant"],
                kind=record["vlak_type"],
                location_id=record["locatie_id"],
                polygon_id=polygon_id,
                review_date=record["controle_datum"],
            )
        )
    if not selected:
        raise ValueError("Geen beoordeelde drinkwaterzuiveringen gevonden.")
    return selected


def _detail_query(reviews: list[ReviewedLocation]) -> str:
    references = {review.polygon_id for review in reviews}
    if "relation/12565283" in references:
        references.add("relation/19326342")  # Reservoirmultipolygoon Berenplaat.
    selectors = []
    for kind in ("way", "relation"):
        identifiers = sorted(
            int(reference.split("/")[1])
            for reference in references
            if reference.startswith(kind + "/")
        )
        if identifiers:
            selectors.append(f"{kind}(id:{','.join(map(str, identifiers))});")
    return (
        "[out:json][timeout:90][maxsize:67108864];"
        f"({''.join(selectors)})->.roots;"
        "way(r.roots)->.members;(.roots;.members;"
        "rel(bw.members)[type=multipolygon];);out geom;"
    )


def _closed_rings(
    segments: list[list[tuple[float, float]]],
) -> list[list[tuple[float, float]]]:
    """Join OSM way segments without inventing a missing closing edge."""
    pending = [segment.copy() for segment in segments]
    rings = []
    while pending:
        ring = pending.pop(0)
        while ring[0] != ring[-1]:
            for index, segment in enumerate(pending):
                if ring[-1] == segment[0]:
                    ring += segment[1:]
                elif ring[-1] == segment[-1]:
                    ring += segment[-2::-1]
                elif ring[0] == segment[-1]:
                    ring = segment[:-1] + ring
                elif ring[0] == segment[0]:
                    ring = segment[:0:-1] + ring
                else:
                    continue
                pending.pop(index)
                break
            else:
                raise ValueError(
                    "OSM-ring is niet gesloten; er wordt geen grens verzonnen."
                )
        if len(ring) < 4:
            raise ValueError("OSM-ring bevat te weinig punten.")
        rings.append(ring)
    return rings


def _coordinates(element: OsmElement) -> list[tuple[float, float]]:
    return [(point["lon"], point["lat"]) for point in element["geometry"]]


def _polygon(element: OsmElement, objects: dict[str, OsmElement]) -> BaseGeometry:
    reference = _osm_id(element)
    if element["type"] == "way":
        coordinates = _coordinates(element)
        if len(coordinates) < 4 or coordinates[0] != coordinates[-1]:
            raise ValueError(f"OSM-vlak is niet gesloten: {reference}")
        result: BaseGeometry = Polygon(coordinates)
    elif element.get("tags", {}).get("type") == "multipolygon":
        outer = []
        inner = []
        for member in element["members"]:
            if member["type"] == "way" and member.get("role", "") in {
                "",
                "outer",
                "inner",
            }:
                destination = inner if member.get("role") == "inner" else outer
                destination.append(_coordinates(member))
        shells = _closed_rings(outer)
        holes: list[list[list[tuple[float, float]]]] = [[] for _ in shells]
        for hole in _closed_rings(inner):
            candidates = [
                index
                for index, shell in enumerate(shells)
                if Polygon(shell).covers(Polygon(hole))
            ]
            if not candidates:
                raise ValueError(f"OSM-binnenring zonder buitenring: {reference}")
            shell_index = min(candidates, key=lambda index: Polygon(shells[index]).area)
            holes[shell_index].append(hole)
        result = MultiPolygon(
            [
                Polygon(shell, shell_holes)
                for shell, shell_holes in zip(shells, holes, strict=True)
            ]
        )
    elif element.get("tags", {}).get("type") == "site":
        parts = []
        for member in element["members"]:
            if member["type"] != "way":
                raise ValueError(f"Niet-ondersteund OSM-site-lid: {reference}")
            member_ref = f"way/{member['ref']}"
            member_element = objects[member_ref]
            if member_element.get("tags"):
                part = member_element
            else:
                parents = [
                    candidate
                    for candidate in objects.values()
                    if candidate.get("tags", {}).get("type") == "multipolygon"
                    and any(
                        item["type"] == "way"
                        and item["ref"] == member["ref"]
                        and item.get("role") == "outer"
                        for item in candidate.get("members", [])
                    )
                ]
                if len(parents) != 1:
                    raise ValueError(
                        f"OSM-site-lid heeft geen eenduidig vlak: {member_ref}"
                    )
                part = parents[0]
            parts.append(_polygon(part, objects))
        result = unary_union(parts)
    else:
        raise ValueError(f"Geen ondersteund OSM-vlak: {reference}")
    if (
        result.is_empty
        or not result.is_valid
        or result.geom_type not in {"Polygon", "MultiPolygon"}
    ):
        raise ValueError(f"Ongeldige OSM-vlakgeometrie: {reference}")
    return result


def _collect_polygons(
    reviews: list[ReviewedLocation], detail: dict[str, Any]
) -> list[DrinkingWaterPolygon]:
    objects = {_osm_id(element): element for element in detail["elements"]}
    missing = {review.polygon_id for review in reviews} - set(objects)
    if missing:
        raise ValueError(
            f"OSM-geometrieantwoord mist vlakken: {', '.join(sorted(missing))}"
        )
    transformer = Transformer.from_crs(
        "EPSG:4326", settings.crs, always_xy=True, allow_ballpark=False
    )
    polygons = []
    for review in reviews:
        geometry = _polygon(objects[review.polygon_id], objects)
        projected = transform(transformer.transform, geometry)
        if not projected.is_valid or projected.is_empty:
            raise ValueError(f"Ongeldige projectie voor OSM-vlak {review.polygon_id}")
        if isinstance(projected, Polygon):
            projected = MultiPolygon([projected])
        polygons.append(
            DrinkingWaterPolygon(
                name=review.name,
                operator=review.operator,
                kind=review.kind,
                location_id=review.location_id,
                polygon_id=review.polygon_id,
                review_date=review.review_date,
                geometry=projected,
            )
        )
    return polygons


def _frame(polygons: list[DrinkingWaterPolygon], timestamp: str) -> gpd.GeoDataFrame:
    rows = [
        {
            "naam": polygon.name,
            "exploitant": polygon.operator,
            "vlak_type": polygon.kind,
            "osm_locatie_id": polygon.location_id,
            "osm_ids": polygon.polygon_id,
            "omschrijving": "Beoordeelde drinkwaterzuivering",
            "controle_datum": polygon.review_date,
            "opmerking": (
                "Gebouwcontour; geen volledige terreingrens."
                if polygon.kind == "gebouw"
                else "Terreingrens niet onafhankelijk geverifieerd."
            ),
            "bron": "OpenStreetMap contributors",
            "licentie": "ODbL 1.0",
            "osm_peildatum_utc": timestamp,
            "geometry": polygon.geometry,
        }
        for polygon in polygons
    ]
    columns = [
        "naam",
        "exploitant",
        "vlak_type",
        "osm_locatie_id",
        "osm_ids",
        "omschrijving",
        "controle_datum",
        "opmerking",
        "bron",
        "licentie",
        "osm_peildatum_utc",
        "geometry",
    ]
    return gpd.GeoDataFrame(
        rows, columns=columns, geometry="geometry", crs=settings.crs
    )


def _write_layers(
    target_path: Path,
    sites: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    *,
    include_buildings: bool,
) -> None:
    """Write validated layers beside the target and replace it atomically."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.", suffix=".gpkg", dir=target_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    matching = gpd.GeoDataFrame(
        pd.concat(
            [sites, buildings] if include_buildings else [sites], ignore_index=True
        ),
        geometry="geometry",
        crs=settings.crs,
    )
    try:
        for index, (layer, features) in enumerate(
            (
                (DRINKWATER_LAYER, matching),
                (SITE_LAYER, sites),
                (BUILDING_LAYER, buildings),
            )
        ):
            write_geopackage_layer(
                features, temporary, layer_name=layer, mode="w" if index == 0 else "a"
            )
        logger.info("Valideren OSM-drinkwater GeoPackage: %s", temporary)
        validate_geopackage(temporary)
        for layer, expected in (
            (DRINKWATER_LAYER, len(matching)),
            (SITE_LAYER, len(sites)),
            (BUILDING_LAYER, len(buildings)),
        ):
            info = pyogrio.read_info(temporary, layer=layer)
            if (
                info["features"] != expected
                or info["crs"] is None
                or not same_crs(info["crs"], settings.crs)
            ):
                raise ValueError(f"Controle van OSM-laag {layer} mislukt.")
        temporary.replace(target_path)
    finally:
        temporary.unlink(missing_ok=True)


def download_osm_drinkwater(
    target_path: Path | None = None,
    *,
    data_store: DataStore | None = None,
    reviews_path: Path | None = None,
    endpoint: str = OVERPASS_ENDPOINT,
    cache_dir: Path | None = None,
    offline: bool = False,
    overwrite: bool = False,
    include_buildings: bool = False,
    timeout: float = 150,
) -> Path:
    """Build drinking-water polygons from OSM in the configured source data.

    Parameters
    ----------
    target_path : pathlib.Path, optional
        GeoPackage output. Defaults to source_data/osm/drinkwaterlocaties.gpkg.
    data_store : DataStore, optional
        Configured Waterlagen data store.
    reviews_path : pathlib.Path, optional
        JSON with reviewed locations. Defaults to the bundled source review.
    endpoint : str, optional
        Overpass API endpoint.
    cache_dir : pathlib.Path, optional
        Directory for validated raw Overpass JSON responses.
    offline : bool, optional
        Read the geometry response from cache without network access.
    overwrite : bool, optional
        Replace a validated existing GeoPackage. Otherwise reuse it.
    include_buildings : bool, optional
        Also include building-only OSM polygons in the BAG matching layer.
    timeout : float, optional
        HTTP timeout in seconds.

    Returns
    -------
    pathlib.Path
        GeoPackage with a BAG matching layer and separate review layers.
        BAG matching uses the existing Waterlagen representative-point rule.
    """
    store = data_store or DataStore()
    target = Path(
        target_path or store.source_data_dir / "osm" / "drinkwaterlocaties.gpkg"
    )
    if target.is_file() and not overwrite:
        validate_geopackage(target)
        info = pyogrio.read_info(target, layer=DRINKWATER_LAYER)
        if (
            info["features"] < 1
            or info["crs"] is None
            or not same_crs(info["crs"], settings.crs)
        ):
            raise ValueError(f"Bestaande OSM-drinkwaterlaag is ongeldig: {target}")
        if "controle_datum" not in info["fields"] or {
            "bewijs",
            "bronnen_functie",
            "osm_urls",
            "licentie_url",
        } & set(info["fields"]):
            raise ValueError(
                f"Bestaande OSM-drinkwaterlaag gebruikt de oude selectie: {target}. "
                "Gebruik --overwrite."
            )
        logger.info("Bestaande OSM-drinkwaterlocaties hergebruikt: %s", target)
        return target
    if offline and cache_dir is None:
        raise ValueError("Offline gebruik vereist cache_dir.")
    if timeout <= 0:
        raise ValueError("timeout moet positief zijn.")
    reviews = _read_reviews(Path(reviews_path or REVIEWS_PATH))
    logger.info("%s beoordeelde drinkwaterzuiveringen geselecteerd", len(reviews))
    detail = _read_overpass(
        _detail_query(reviews),
        "geometrie",
        endpoint=endpoint,
        cache_dir=cache_dir,
        offline=offline,
        timeout=timeout,
    )
    timestamp = detail.get("osm3s", {}).get("timestamp_osm_base")
    if not isinstance(timestamp, str) or not timestamp:
        raise ValueError("Overpass-geometrieantwoord mist de OSM-peildatum.")
    polygons = _collect_polygons(reviews, detail)
    sites = _frame(
        [polygon for polygon in polygons if polygon.kind == "terrein"], timestamp
    )
    buildings = _frame(
        [polygon for polygon in polygons if polygon.kind == "gebouw"], timestamp
    )
    if sites.empty and not include_buildings:
        raise ValueError("Geen OSM-terreinvakken voor BAG-koppeling gevonden.")
    _write_layers(target, sites, buildings, include_buildings=include_buildings)
    logger.info(
        "OSM-drinkwaterlocaties opgeslagen: %s (%s terreinen, %s gebouwcontouren)",
        target,
        len(sites),
        len(buildings),
    )
    return target
