"""Record object-level contributions without changing the burn calculation."""

import json
from pathlib import Path

import numpy as np
import rasterio

from waterlagen._production import _file_identity
from waterlagen.raster.grid import RasterGrid

from .waternet import waternet_path

TRACE_FILENAME = "duiker_inbranding.json"


def _burn_counts(
    watersysteem: Path,
    grid: RasterGrid,
    original: np.ndarray,
    burned: np.ndarray,
    signature: str,
) -> dict | None:
    """Count winning, covered and changed cells per registration on this grid."""
    path = waternet_path(watersysteem, grid)
    if not path.exists():
        return None
    with rasterio.open(path) as source:
        if source.count < 5 or "duiker_ids" not in source.tags():
            return None
        owners = source.read(5, out_dtype="int32")
        identifiers = json.loads(source.tags()["duiker_ids"])
    winning = owners > 0
    covered = winning & np.isfinite(original)
    original_values = original[covered]
    if np.issubdtype(burned.dtype, np.integer):
        original_values = np.rint(original_values)
    changed = burned[covered] != original_values.astype(burned.dtype)
    size = max((int(value) for value in identifiers), default=0) + 1
    winners = np.bincount(owners[winning], minlength=size)
    valid = np.bincount(owners[covered], minlength=size)
    applied = np.bincount(owners[covered][changed], minlength=size)
    return {
        "burn_signature": signature,
        "waternet": _file_identity(path),
        "objects": {
            identifier: {
                "winnend": int(winners[int(code)]),
                "geldige_dem": int(valid[int(code)]),
                "toegepast": int(applied[int(code)]),
            }
            for code, identifier in identifiers.items()
        },
    }


def _write_burn_counts(data: dict | None, dem_path: Path) -> None:
    """Publish only after the corresponding DEM has been successfully replaced."""
    path = dem_path.with_name(TRACE_FILENAME)
    if data is None:
        path.unlink(missing_ok=True)
        return
    data["dem"] = _file_identity(dem_path)
    temporary = path.with_suffix(".tmp.json")
    try:
        temporary.write_text(json.dumps(data), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_burn_counts(dem_paths: list[Path]) -> tuple[dict[str, dict[str, int]], bool]:
    """Missing or stale evidence never establishes a negative burn result."""
    totals: dict[str, dict[str, int]] = {}
    complete = bool(dem_paths)
    for path in dem_paths:
        try:
            data = json.loads(
                path.with_name(TRACE_FILENAME).read_text(encoding="utf-8")
            )
            with rasterio.open(path) as source:
                signature = source.tags().get("waterlagen_burn")
            waternet = data["waternet"]
            if (
                data["dem"] != _file_identity(path)
                or signature != data["burn_signature"]
                or waternet != _file_identity(Path(waternet["path"]))
            ):
                complete = False
                continue
            objects = data["objects"]
            fields = {"winnend", "geldige_dem", "toegepast"}
            valid_counts = isinstance(objects, dict) and all(
                isinstance(counts, dict)
                and set(counts) == fields
                and all(type(value) is int and value >= 0 for value in counts.values())
                and counts["toegepast"] <= counts["geldige_dem"] <= counts["winnend"]
                for counts in objects.values()
            )
            if not valid_counts:
                complete = False
                continue
            for identifier, counts in objects.items():
                total = totals.setdefault(identifier, dict.fromkeys(counts, 0))
                for key, value in counts.items():
                    total[key] += value
        except (OSError, ValueError, KeyError, TypeError):
            complete = False
    return totals, complete
