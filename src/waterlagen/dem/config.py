"""Explicit distances and output settings for DEM production."""

from dataclasses import dataclass, field
from math import isfinite

from waterlagen.raster.config import RasterOutputConfig


@dataclass(frozen=True)
class DemConfig:
    """DEM distances in metres, percentile in percent; AHN storage is retained.

    Parameters
    ----------
    building_initial_buffer_m : float
        First exterior search radius, default 1 m.
    building_buffer_step_m : float
        Radius increment without an original donor, default 1 m.
    building_percentile : float
        Percentile at the first successful radius, default 75.
    building_max_search_distance_m : float
        Final radius, default 5 m. Unresolved buildings remain NoData.
    interpolation_max_distance_m : float
        AHN filling distance, default 250 m. Zero disables interpolation.
    output : RasterOutputConfig
        Tile block sizes and overview factors.
    """

    building_initial_buffer_m: float = 1.0
    building_buffer_step_m: float = 1.0
    building_percentile: float = 75.0
    building_max_search_distance_m: float = 5.0
    interpolation_max_distance_m: float = 250.0
    output: RasterOutputConfig = field(default_factory=RasterOutputConfig)

    def __post_init__(self) -> None:
        for name in (
            "building_initial_buffer_m",
            "building_buffer_step_m",
            "building_max_search_distance_m",
        ):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.building_initial_buffer_m > self.building_max_search_distance_m:
            raise ValueError("Initial building buffer exceeds maximum search distance")
        if (
            not isfinite(self.building_percentile)
            or not 0 <= self.building_percentile <= 100
        ):
            raise ValueError("building_percentile must be between 0 and 100")
        if (
            not isfinite(self.interpolation_max_distance_m)
            or self.interpolation_max_distance_m < 0
        ):
            raise ValueError(
                "interpolation_max_distance_m must be finite and non-negative"
            )
