"""Register bundled QGIS layer styles in GeoPackages."""

from pathlib import Path
import sqlite3

from waterlagen.logger import get_logger

logger = get_logger(__name__)

STYLES_DIR = Path(__file__).parent / "styles"

_CREATE_LAYER_STYLES_TABLE = """
CREATE TABLE IF NOT EXISTS layer_styles (
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    f_table_catalog TEXT(256),
    f_table_schema TEXT(256),
    f_table_name TEXT(256),
    f_geometry_column TEXT(256),
    styleName TEXT(30),
    styleQML TEXT,
    styleSLD TEXT,
    useAsDefault BOOLEAN,
    description TEXT,
    owner TEXT(30),
    ui TEXT(30),
    update_time DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
)
"""


def _style_path(layer_name: str) -> Path:
    """Return the bundled QML path associated with a GeoPackage layer name."""
    return STYLES_DIR / f"{layer_name}.qml"


def add_layer_style(geopackage_path: Path, layer_name: str) -> bool:
    """Register a bundled QML style for one GeoPackage layer when available.

    Existing registrations for the same layer and style name are replaced, so a
    repeated layer write leaves exactly one current default style. Layers that
    have no matching QML file are left unchanged.

    Parameters
    ----------
    geopackage_path : pathlib.Path
        Existing GeoPackage containing ``layer_name``.
    layer_name : str
        Name of the GeoPackage layer and corresponding QML stem.

    Returns
    -------
    bool
        ``True`` when a bundled style was registered, otherwise ``False``.
    """
    style_path = _style_path(layer_name)
    if not style_path.is_file():
        return False

    connection = sqlite3.connect(geopackage_path)
    try:
        connection.execute(_CREATE_LAYER_STYLES_TABLE)
        connection.execute(
            """
            INSERT OR IGNORE INTO gpkg_contents (
                table_name,
                data_type,
                identifier,
                description,
                srs_id
            )
            VALUES ('layer_styles', 'attributes', 'layer_styles', '', 0)
            """
        )
        connection.execute(
            """
            DELETE FROM layer_styles
            WHERE f_table_name = ? AND styleName = ?
            """,
            (layer_name, style_path.stem),
        )
        connection.execute(
            """
            INSERT INTO layer_styles (
                f_table_catalog,
                f_table_schema,
                f_table_name,
                f_geometry_column,
                styleName,
                styleQML,
                styleSLD,
                useAsDefault,
                description,
                owner,
                ui
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "",
                "",
                layer_name,
                "geom",
                style_path.stem,
                style_path.read_text(encoding="utf-8"),
                "",
                True,
                f"Waterlagen style for layer: {layer_name}",
                "",
                None,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    logger.info(
        "Registered bundled QGIS style %s for GeoPackage layer %s",
        style_path.name,
        layer_name,
    )
    return True
