import sqlite3

import geopandas as gpd
from shapely.geometry import LineString

from waterlagen._geopackage import write_geopackage_layer
from waterlagen._styles import STYLES_DIR
from waterlagen.settings import settings


def _lines() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"name": ["line"]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs=settings.crs,
    )


def _registered_styles(path):
    with sqlite3.connect(path) as connection:
        return connection.execute(
            """
            SELECT f_table_name, styleName, styleQML, useAsDefault
            FROM layer_styles
            ORDER BY id
            """
        ).fetchall()


def test_write_geopackage_layer_registers_bundled_style(tmp_path):
    geopackage_path = tmp_path / "styled.gpkg"

    write_geopackage_layer(
        _lines(),
        geopackage_path,
        layer_name="hydroobject_segment",
        mode="w",
    )

    assert _registered_styles(geopackage_path) == [
        (
            "hydroobject_segment",
            "hydroobject_segment",
            (STYLES_DIR / "hydroobject_segment.qml").read_text(encoding="utf-8"),
            1,
        )
    ]


def test_write_geopackage_layer_without_style_writes_normally(tmp_path):
    geopackage_path = tmp_path / "unstyled.gpkg"

    write_geopackage_layer(
        _lines(),
        geopackage_path,
        layer_name="zonder_stijl",
        mode="w",
    )

    assert gpd.read_file(geopackage_path, layer="zonder_stijl").shape[0] == 1
    with sqlite3.connect(geopackage_path) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    assert ("layer_styles",) not in tables


def test_repeated_layer_write_replaces_existing_style_registration(tmp_path):
    geopackage_path = tmp_path / "repeated.gpkg"

    write_geopackage_layer(
        _lines(),
        geopackage_path,
        layer_name="hydroobject_segment",
        mode="w",
    )
    write_geopackage_layer(
        _lines(),
        geopackage_path,
        layer_name="hydroobject_segment",
        mode="a",
    )

    assert len(_registered_styles(geopackage_path)) == 1
