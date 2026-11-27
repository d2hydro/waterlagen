"""Controleer de publicatiekeuze en de opslag van AHN-tegels."""

from importlib import import_module
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pytest
import rasterio
import requests
from rasterio.transform import from_origin
from shapely.geometry import box

from waterlagen._sources import SourcePreparation
from waterlagen.ahn import dekking, productie
from waterlagen.datastore import DataStore


@pytest.fixture
def tile(tmp_path):
    path = tmp_path / "bron.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=32,
        height=32,
        count=1,
        dtype="float32",
        crs=28992,
        transform=from_origin(12000, 377016, 0.5, 0.5),
        nodata=-9999,
        tiled=True,
        blockxsize=16,
        blockysize=16,
    ) as ds:
        ds.write(np.ones((32, 32), dtype=np.float32), 1)
    return path


def select_tile(monkeypatch, field, url):
    area = box(12000, 377000, 12016, 377016)
    index = gpd.GeoDataFrame({field: [url]}, geometry=[area], index=["M_01"], crs=28992)
    monkeypatch.setattr(productie, "get_tiles_features", lambda **kwargs: index)
    return area


def serve_tile(monkeypatch, url, tile):
    def get(requested, **kwargs):
        assert requested == url
        response = requests.Response()
        response.status_code = 200
        response._content = tile.read_bytes()
        response.headers["Content-Type"] = "image/tiff"
        return response

    monkeypatch.setattr(import_module("waterlagen.ahn.download"), "http_get", get)


def test_custom_ahn6_folder_keeps_ahn4_download_in_ahn4_folder(
    tmp_path, monkeypatch, tile
):
    store = DataStore(_env_file=(), data_dir=tmp_path, ahn6_data_dir=tmp_path / "eigen")
    url = "https://example.invalid/M_01.tif"
    area = select_tile(monkeypatch, "url", url)
    serve_tile(monkeypatch, url, tile)
    paths = productie._prepare_version(store, area, SourcePreparation(), 4)
    assert paths == [store.ahn_tiles(4) / "M_01.tif"]
    assert paths[0].is_file()


def test_reuse_validates_existing_tile_once(tmp_path, monkeypatch, tile):
    store = DataStore(
        _env_file=(), data_dir=tmp_path, ahn_download_dir=tmp_path / "extra"
    )
    area = select_tile(monkeypatch, "url", "https://example.invalid/M_01.tif")
    cached = store.ahn_tiles(4) / "M_01.tif"
    cached.parent.mkdir(parents=True)
    tile.rename(cached)
    with patch.object(
        productie, "_is_valid_ahn_tile", wraps=productie._is_valid_ahn_tile
    ) as check:
        assert productie._prepare_version(store, area, SourcePreparation(), 4) == [
            cached
        ]
    check.assert_called_once_with(cached)


def test_download_uses_actual_publication_url_and_year(tmp_path, monkeypatch, tile):
    store = DataStore(_env_file=(), data_dir=tmp_path)
    planned = "AHN6_2025_M_012000_377000"
    name = "AHN6_2026_M_12000_377000"
    actual_url = f"https://example.invalid/published/{name}.TIF"
    area = select_tile(
        monkeypatch, "dtm_05", f"https://example.invalid/planning/{planned}.tif"
    )
    publication = dekking.Publication(
        0, "", "", frozenset({planned, name}), {name: actual_url}
    )
    monkeypatch.setattr(dekking, "refresh", lambda *args: publication)
    serve_tile(monkeypatch, actual_url, tile)
    paths = productie._prepare_version(store, area, SourcePreparation(), 6)
    assert paths == [store.ahn_tiles(6) / f"{name}.tif"]
    assert paths[0].is_file()
