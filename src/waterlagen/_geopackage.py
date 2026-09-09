"""Generic GeoPackage writing helpers."""

from pathlib import Path
from typing import Literal

import geopandas as gpd

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
