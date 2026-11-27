"""Check AHN coverage for the selected area."""

from functools import lru_cache
from pathlib import Path
from threading import Lock, Thread

import geopandas as gpd

from waterlagen._sources import SourcePreparation
from waterlagen.ahn import dekking
from waterlagen.areas import area_from_bounds, area_from_file, resolve_area
from waterlagen.datastore import DataStore


@lru_cache(maxsize=8)
def _required(
    arguments: tuple[str, ...], cache: Path, modified: int
) -> dekking.RequiredSheets:
    store = DataStore()
    flag, *values = arguments
    if flag == "--bounds":
        area = area_from_bounds(values)
    elif flag == "--area-file":
        area = area_from_file(Path(values[0]), layer=values[2])
    else:
        area = resolve_area(values[0], store, SourcePreparation(offline=True))
    geometry = gpd.GeoSeries([area.geometry], crs=area.crs).to_crs(28992).iloc[0]
    return dekking.required(geometry)


class CoveragePreview:
    """Share one AHN6 update across coverage requests."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.phase = "ready"
        self.error = ""

    def _refresh(self, cache: Path, force: bool) -> None:
        def phase(value: str) -> None:
            with self.lock:
                self.phase = value

        try:
            dekking.refresh(cache, phase, force=force)
        except Exception as error:
            with self.lock:
                self.phase = "error"
                self.error = str(error)
        else:
            phase("ready")

    def status(self, arguments: tuple[str, ...], *, force: bool = False) -> dict:
        cache = DataStore().ahn_cache()
        modified = (
            Path(arguments[1]).stat().st_mtime_ns
            if arguments[0] == "--area-file"
            else 0
        )
        needed = _required(arguments, cache, modified)
        with self.lock:
            published = dekking.publication(cache)
            busy = self.phase in {"checking", "download"}
            if not busy and (force or (not published.fresh and self.phase != "error")):
                self.phase = "checking"
                self.error = ""
                Thread(target=self._refresh, args=(cache, force), daemon=True).start()
            counts = {
                str(version): needed.counts(version, published) for version in (4, 5, 6)
            }
            return dict(
                phase=self.phase,
                checked=published.checked,
                counts=counts,
                error=self.error,
            )
