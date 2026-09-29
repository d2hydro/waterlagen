"""Source provenance and bounded nearest-neighbour filling of land-use gaps."""

import json
from math import ceil, isfinite
from pathlib import Path

import numpy as np
import rasterio as rio

# Stable IDs, independent of CSV ordering, optional sources and burn priority.
SOURCE_LAYERS = {
    1: "BGT:bgt_ondersteunendwaterdeel",
    2: "BGT:bgt_begroeidterreindeel",
    3: "BGT:bgt_onbegroeidterreindeel",
    4: "TOP10NL:top10nl_functioneel_gebied_vlak",
    5: "TOP10NL:top10nl_functioneel_gebied_multivlak",
    6: "TOP10NL:top10nl_terrein_vlak",
    7: "BRP:brp_gewas",
    8: "BGT:bgt_ondersteunendwegdeel",
    9: "BGT:bgt_wegdeel",
    10: "BAG:pand",
    11: "HyDAMO:gemaal",
    12: "BGT:bgt_waterdeel",
}
DONOR_ALLOWED = {code: code not in {6, 7, 10} for code in SOURCE_LAYERS}
FILL_VERSION = "1"


def _source_path(target: Path) -> Path:
    # Separate directory prevents the land-use VRT from mixing the two products.
    return target.parent / "bronnen" / target.name


def _validate_radius(radius_m: float) -> None:
    if not isfinite(radius_m) or radius_m < 0:
        raise ValueError("gap_fill_distance_m must be finite and non-negative")


def _fill_gaps(
    values: np.ndarray,
    sources: np.ndarray,
    land: np.ndarray,
    *,
    radius_m: float,
    pixel_width: float,
    pixel_height: float,
) -> int:
    """Copy original eligible donors once, in Euclidean distance order.

    Distances are between cell centres. Ties prefer the northernmost, then
    westernmost donor. Explicit NoData with a source ID is protected.
    Offset slices keep memory bounded without full-size distance/index arrays.
    """
    _validate_radius(radius_m)
    if radius_m == 0:
        return 0
    donors = (values != 0) & np.isin(
        sources, [code for code, allowed in DONOR_ALLOWED.items() if allowed]
    )
    pending = (values == 0) & (sources == 0) & land
    if not donors.any() or not pending.any():
        return 0
    rows, cols = values.shape
    offsets = []
    for dy in range(-ceil(radius_m / pixel_height), ceil(radius_m / pixel_height) + 1):
        for dx in range(
            -ceil(radius_m / pixel_width), ceil(radius_m / pixel_width) + 1
        ):
            distance2 = (dy * pixel_height) ** 2 + (dx * pixel_width) ** 2
            if 0 < distance2 <= radius_m**2:
                offsets.append((distance2, dy, dx))
    count = 0
    for _, dy, dx in sorted(offsets):
        y0, y1 = max(0, -dy), min(rows, rows - dy)
        x0, x1 = max(0, -dx), min(cols, cols - dx)
        if y0 >= y1 or x0 >= x1:
            continue
        target = np.s_[y0:y1, x0:x1]
        donor = np.s_[y0 + dy : y1 + dy, x0 + dx : x1 + dx]
        selected = pending[target] & donors[donor]
        count += int(selected.sum())
        values[target][selected] = values[donor][selected]
        sources[target][selected] = sources[donor][selected]
        pending[target][selected] = False
        if not pending.any():
            break
    return count


def _fill_metadata(radius_m: float) -> dict[str, str]:
    return {
        "gap_fill_version": FILL_VERSION,
        "gap_fill_distance_m": str(float(radius_m)),
        "source_layers": json.dumps(SOURCE_LAYERS, sort_keys=True),
        "donor_allowed": json.dumps(DONOR_ALLOWED, sort_keys=True),
    }


def _validate_outputs(target: Path, radius_m: float) -> None:
    """Refuse reuse of old, incomplete or differently configured output pairs."""
    pair_id = None
    grid = None
    for path in (target, _source_path(target)):
        if not path.is_file():
            raise FileNotFoundError(
                f"Output missing: {path}. Rebuild with overwrite=True."
            )
        with rio.open(path) as raster:
            if any(
                raster.tags().get(key) != value
                for key, value in _fill_metadata(radius_m).items()
            ):
                raise ValueError(
                    f"Output settings differ: {path}. Rebuild with overwrite=True."
                )
            current_pair = raster.tags().get("output_pair")
            current_grid = (raster.crs, raster.transform, raster.width, raster.height)
            if not current_pair or (
                pair_id is not None
                and (pair_id != current_pair or grid != current_grid)
            ):
                raise ValueError(
                    f"Output pair differs: {path}. Rebuild with overwrite=True."
                )
            pair_id, grid = current_pair, current_grid
