"""Resolve Waterlagen paths before opening a datastore."""

from pathlib import Path


def ahn_tile_directory(sources: Path, version: int, root: Path | None = None) -> Path:
    """Return the default tile directory for an AHN generation."""
    if root is not None:
        return root / f"AHN{version}"
    ahn = sources / "ahn"
    if version != 4:
        ahn = ahn / f"ahn{version}"
    return ahn / "dtm_05"
