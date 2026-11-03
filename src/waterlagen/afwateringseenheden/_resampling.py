"""Supported DEM resampling methods shared by Python and CLI entry points."""

from rasterio.enums import Resampling

DEM_RESAMPLING_METHODS = (
    "nearest",
    "bilinear",
    "cubic",
    "cubic_spline",
    "lanczos",
    "average",
    "min",
    "max",
    "med",
    "q1",
    "q3",
)


def _validate_dem_resampling(value: str) -> Resampling:
    """Return the warp enum for a canonical supported method."""
    if value not in DEM_RESAMPLING_METHODS:
        raise ValueError(
            f"Invalid dem_resampling {value!r}; choose from "
            + ", ".join(DEM_RESAMPLING_METHODS)
        )
    return Resampling[value]
