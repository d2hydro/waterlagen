"""Check which AHN terrain tiles are available for an area."""

import gzip
import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from functools import cached_property, lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from urllib.parse import urljoin, urlsplit

import geopandas as gpd
import numpy as np
import requests
import shapely
from shapely.geometry.base import BaseGeometry

from waterlagen._http import get

DATA = Path(__file__).with_name("bladindex")
MANIFEST = "https://basisdata.nl/hwh-portal/20230609_tmp/links/nationaal/Nederland/AHN6_KM_DTM05.json"
MAX_AGE = 24 * 3600
_refresh_lock = Lock()


def sheet_location(tile: str) -> str:
    """Return the RD coordinate key shared by planning and published filenames."""
    x, y = tile.rsplit("_M_", 1)[-1].split("_")
    return f"{int(x)}_{int(y)}"


@dataclass(frozen=True)
class Publication:
    checked: float
    etag: str
    url: str
    tiles: frozenset[str]

    urls: dict[str, str] = field(default_factory=dict)

    @cached_property
    def by_location(self) -> dict[str, str]:
        """Index the latest published survey for each RD location."""
        return {sheet_location(tile): tile for tile in sorted(self.tiles)}

    @property
    def fresh(self) -> bool:
        return 0 <= time.time() - self.checked < MAX_AGE


@lru_cache(maxsize=4)
def _read(path: Path, modified: int) -> Publication:
    data = json.loads(gzip.decompress(path.read_bytes()))
    return Publication(
        data["checked"],
        data["etag"],
        data["url"],
        frozenset(data["tiles"]),
        data.get("urls", {}),
    )


def publication(cache: Path) -> Publication:
    """Read the latest local AHN6 tile list."""
    path = cache / "publicatie-ahn6.json.gz"
    bundled = DATA / "ahn6.json.gz"
    baseline = _read(bundled, bundled.stat().st_mtime_ns)
    try:
        saved = _read(path, path.stat().st_mtime_ns)
    except (OSError, EOFError, ValueError, KeyError):
        return baseline
    return max((baseline, saved), key=lambda item: item.checked)


def _fetch(
    url: str, previous: Publication, progress: Callable[[str], None]
) -> Publication:
    with get(
        url, headers={"If-None-Match": previous.etag}, stream=True, timeout=(8, 25)
    ) as response:
        if response.status_code == 304:
            return replace(previous, checked=time.time(), url=response.url)
        response.raise_for_status()
        progress("download")
        urls = {}
        for feature in response.json()["features"]:
            url = urljoin(response.url, feature["properties"]["file"])
            filename = Path(urlsplit(url).path).name.upper()
            if not re.fullmatch(r"AHN6_\d{4}_M_\d+_\d+\.TIF", filename):
                raise ValueError("Onverwachte bestandsnaam in de AHN6-publicatielijst.")
            urls[filename[:-4]] = url
        if not urls:
            raise ValueError("De AHN6-publicatielijst is leeg.")
        return Publication(
            time.time(),
            response.headers.get("ETag", ""),
            response.url,
            frozenset(urls),
            urls,
        )


def refresh(
    cache: Path, progress: Callable[[str], None], *, force: bool = False
) -> Publication:
    """Update the AHN6 tile list if it is older than 24 hours."""
    with _refresh_lock:
        previous = publication(cache)
        if previous.fresh and not force:
            return previous
        try:
            current = _fetch(previous.url, previous, progress)
        except requests.RequestException:
            if previous.url == MANIFEST:
                raise
            current = _fetch(MANIFEST, previous, progress)
        cache.mkdir(parents=True, exist_ok=True)
        target = cache / "publicatie-ahn6.json.gz"
        with NamedTemporaryFile(dir=cache, delete=False) as temp:
            path = Path(temp.name)
        try:
            payload = {**asdict(current), "tiles": sorted(current.tiles)}
            path.write_bytes(
                gzip.compress(json.dumps(payload).encode(), compresslevel=1)
            )
            path.replace(target)
        finally:
            path.unlink(missing_ok=True)
        return current


@lru_cache(maxsize=2)
def _grid(filename: str) -> gpd.GeoDataFrame:
    return gpd.read_parquet(DATA / filename)


def _selected(filename: str, geometry: BaseGeometry) -> gpd.GeoDataFrame:
    grid = _grid(filename)
    # Positive-area overlap excludes sheets which only touch the outer boundary.
    hits = grid.sindex.query(geometry, predicate="intersects")
    candidates = grid.iloc[hits]
    return candidates.loc[~shapely.touches(geometry, candidates.geometry.array)]


@dataclass(frozen=True)
class RequiredSheets:
    count_top: int
    available4: int
    available5: int
    kilometer: frozenset[str]

    def counts(self, version: int, published: Publication) -> tuple[int, int]:
        """Return published and required sheets, restricted to the selected area."""
        if version == 6:
            return len(self.kilometer & published.by_location.keys()), len(
                self.kilometer
            )
        return (self.available4 if version == 4 else self.available5), self.count_top


def required(geometry: BaseGeometry) -> RequiredSheets:
    """Find required DTM sheets on the official grids, in EPSG:28992."""
    shapely.prepare(geometry)
    top = _selected("top.parquet", geometry)
    km = _selected("kilometer.parquet", geometry)
    return RequiredSheets(
        len(top),
        int(np.sum(top.ahn4)),
        int(np.sum(top.ahn5)),
        frozenset(sheet_location(tile) for tile in km.tile_id),
    )


def check_version(
    geometry: BaseGeometry, crs: str, version: int, cache: Path, *, offline: bool
) -> None:
    """Require every selected sheet when using a single AHN version."""
    published = publication(cache)
    if version == 6 and not offline:
        published = refresh(cache, lambda _: None)
    if version == 6 and not published.fresh:
        raise ValueError("AHN6-dekking onbekend: controleer de publicatielijst online.")
    rd = gpd.GeoSeries([geometry], crs=crs).to_crs(28992).iloc[0]
    available, total = required(rd).counts(version, published)
    if not total or available != total:
        raise ValueError(
            f"AHN{version}: {available} van {total} benodigde tegels beschikbaar."
        )
