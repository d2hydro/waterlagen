"""Write the selected burn inputs together for inspection in QGIS."""

from pathlib import Path

import geopandas as gpd

from waterlagen._crs import read_layer_crs_info, same_crs
from waterlagen._downloads import _temporary_path, validate_geopackage
from waterlagen._filesystem import replace_file
from waterlagen._geopackage import write_geopackage_layer
from waterlagen.logger import get_logger

from .sources import WatersysteemSources

logger = get_logger(__name__)


def _write_brandlagen_overzicht(
    sources: WatersysteemSources,
    optional: gpd.GeoDataFrame,
    path: Path,
) -> Path:
    """Atomically replace the overview, including empty layers and removing stale ones.

    This is selected vector input, not the final raster treatment. Preserve
    source attributes and geometries; keep each optional source in its own layer.
    """
    layers = {
        "hydamo_primair": sources.primary,
        "hydamo_secundair": sources.secondary,
        "hydamo_tertiair": sources.tertiary,
        "hydamo_duikers": sources.culverts,
    }
    for code, features in optional.groupby("broncode", sort=True):
        name = str(features.bronlaag.iloc[0])
        if name in layers:
            name = f"bron_{int(code)}_{name}"
        while name in layers:
            name = f"bron_{int(code)}_{name}"
        layers[name] = features

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(path, suffix=".gpkg")
    temporary.unlink(missing_ok=True)
    expected = {}
    try:
        for name, features in layers.items():
            if features is None:
                continue
            if features.crs is None:
                raise ValueError(f"Brandlagenoverzicht: {name} heeft geen CRS")
            logger.info(
                "Writing burn input overview layer %s (%s features)",
                name,
                len(features),
            )
            write_geopackage_layer(
                features, temporary, layer_name=name, mode="a" if expected else "w"
            )
            expected[name] = features.crs
        validate_geopackage(temporary)
        actual = {info.layer: info.crs for info in read_layer_crs_info(temporary)}
        if set(actual) != set(expected) or any(
            actual[name] is None or not same_crs(actual[name], crs)
            for name, crs in expected.items()
        ):
            raise ValueError("Brandlagenoverzicht heeft afwijkende lagen of CRS")
        replace_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    logger.info("Burn input overview written: %s", path)
    return path
