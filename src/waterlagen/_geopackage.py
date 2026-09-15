"""Generic GeoPackage writing helpers."""

import os
import tempfile
from pathlib import Path
from typing import Literal

import geopandas as gpd

from waterlagen._crs import read_layer_crs_info, same_crs
from waterlagen._downloads import validate_geopackage
from waterlagen._styles import add_layer_style


def write_geopackage_layer(
    features: gpd.GeoDataFrame,
    geopackage_path: Path,
    *,
    layer_name: str,
    mode: Literal["w", "a"],
) -> None:
    """Write one GeoPackage layer and register a bundled QGIS style if present.

    Parameters
    ----------
    features : geopandas.GeoDataFrame
        Features to write.
    geopackage_path : pathlib.Path
        Target GeoPackage path.
    layer_name : str
        Output layer name. A matching ``styles/<layer_name>.qml`` is registered
        in the GeoPackage ``layer_styles`` table after the layer is written.
    mode : {"w", "a"}
        GeoPackage write mode. Use ``"w"`` for the first layer and ``"a"`` for
        later layers.
    """
    geopackage_path = Path(geopackage_path)
    features.to_file(
        geopackage_path,
        layer=layer_name,
        driver="GPKG",
        index=False,
        mode=mode,
    )
    add_layer_style(geopackage_path, layer_name)


def write_geopackage_layer_atomically(
    features: gpd.GeoDataFrame,
    geopackage_path: Path,
    *,
    layer_name: str,
) -> None:
    """Write, validate, and atomically replace a single-layer GeoPackage.

    The output is first written beside its destination. Its GeoPackage structure
    and CRS are verified before it replaces an existing product.
    """
    if features.crs is None:
        raise ValueError("GeoPackage output features have no CRS")

    geopackage_path = Path(geopackage_path)
    geopackage_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{geopackage_path.name}.",
        suffix=".gpkg",
        dir=geopackage_path.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink(missing_ok=True)
    try:
        write_geopackage_layer(
            features,
            temporary_path,
            layer_name=layer_name,
            mode="w",
        )
        validate_geopackage(temporary_path)
        output_layer = next(
            (
                layer_info
                for layer_info in read_layer_crs_info(temporary_path)
                if layer_info.layer == layer_name
            ),
            None,
        )
        if output_layer is None or output_layer.crs is None:
            raise ValueError(f"Written {layer_name} layer has no CRS")
        if not same_crs(features.crs, output_layer.crs):
            raise ValueError(f"Written {layer_name} layer has a changed CRS")
        temporary_path.replace(geopackage_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
