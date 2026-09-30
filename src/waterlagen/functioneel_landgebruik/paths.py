"""Product paths for tile folders, with support for legacy flat tiles."""

from pathlib import Path


def source_path(target: Path) -> Path:
    """Return the source raster for a new or legacy land-use tile."""
    if target.name == "functioneel_landgebruik.tif":
        return target.with_name("functioneel_landgebruik_bronnen.tif")
    return target.parent / "bronnen" / target.name


def building_paths(target: Path) -> tuple[Path, Path]:
    """Return the building-ID raster and complete prepared footprints."""
    if target.name == "functioneel_landgebruik.tif":
        return target.with_name("gebouw_ids.tif"), target.with_name("gebouwen.gpkg")
    return (
        target.parent / "gebouw_ids" / target.name,
        target.parent / "gebouwen" / target.with_suffix(".gpkg").name,
    )
