"""Generic GeoPackage writing helpers."""

import os
from contextlib import closing
import tempfile
import sqlite3
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
    preserve_other_layers: bool = False,
) -> None:
    """Write, validate, and atomically replace a GeoPackage layer.

    The output is first written beside its destination. Its GeoPackage structure
    and CRS are verified before it replaces an existing product.
    With ``preserve_other_layers=True``, copy the existing database (including
    committed WAL changes) first and replace only the requested layer.
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
        if preserve_other_layers and geopackage_path.exists():
            with closing(sqlite3.connect(geopackage_path)) as source:
                with closing(sqlite3.connect(temporary_path)) as destination:
                    source.backup(destination)
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
