from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.errors import WindowError
from rasterio.transform import from_origin
from shapely.geometry import box

from waterlagen.ahn import interpolate


def _write_raster(path, data, *, nodata=-9999.0, scale=1.0):
    height, width = data.shape
    transform = from_origin(0.0, float(height), 1.0, 1.0)
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": data.dtype,
        "crs": "EPSG:28992",
        "transform": transform,
        "nodata": nodata,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.scales = (scale,)


def test_tiles_series_from_vrt_respects_indices(tmp_path, monkeypatch):
    tif_a = tmp_path / "A.tif"
    tif_b = tmp_path / "B.tif"
    data = np.ones((2, 2), dtype=np.float32)
    _write_raster(tif_a, data)
    _write_raster(tif_b, data)

    monkeypatch.setattr(
        interpolate, "list_tif_files_in_vrt_file", lambda vrt_file: [tif_a, tif_b]
    )

    series = interpolate._tiles_series_from_vrt(vrt_file=tif_a, indices=["B"])

    assert list(series.index) == ["B"]
    assert tuple(series["B"].bounds) == (0.0, 0.0, 2.0, 2.0)
    assert series.crs.to_epsg() == 28992


def test_interpolate_within_geometry_fills_nodata(tmp_path):
    tif = tmp_path / "src.tif"
    data = np.full((6, 6), 10.0, dtype=np.float32)
    data[2, 2] = -9999.0
    _write_raster(tif, data, nodata=-9999.0)

    with rasterio.open(tif) as src:
        out, transform = interpolate.interpolate_within_geometry(
            src=src,
            geometry=box(0, 0, 6, 6),
            max_search_distance=2,
        )

    assert out.shape == (6, 6)
    assert np.isfinite(out[2, 2])
    assert out[2, 2] != -9999.0
    assert transform.a == 1.0


def test_interpolate_within_geometry_raises_for_empty_window(tmp_path):
    tif = tmp_path / "src.tif"
    data = np.ones((4, 4), dtype=np.float32)
    _write_raster(tif, data)

    with rasterio.open(tif) as src:
        with pytest.raises((ValueError, WindowError)):
            interpolate.interpolate_within_geometry(
                src=src,
                geometry=box(100, 100, 110, 110),
                max_search_distance=1,
            )


def test_interpolate_ahn_tiles_writes_result_without_vrt(tmp_path, monkeypatch):
    src_tif = tmp_path / "source.tif"
    data = np.full((32, 32), 7, dtype=np.int16)
    _write_raster(src_tif, data, nodata=-9999, scale=0.5)

    monkeypatch.setattr(
        interpolate,
        "_tiles_series_from_vrt",
        lambda vrt_file, indices=None: gpd.GeoSeries(
            {"tileA": box(0, 0, 32, 32)}, crs="EPSG:28992"
        ),
    )
    monkeypatch.setattr(
        interpolate, "datastore", SimpleNamespace(processed_data_dir=tmp_path)
    )

    out_dir = interpolate.interpolate_ahn_tiles(
        ahn_vrt_file=src_tif,
        create_vrt=False,
        dir_name="ahn_filled_test",
    )

    out_tif = out_dir / "tileA.tif"
    assert out_dir == tmp_path / "ahn_filled_test"
    assert out_tif.exists()
    with rasterio.open(out_tif) as src:
        assert src.width == 32
        assert src.height == 32
        assert src.scales[0] == 0.5


def test_interpolate_ahn_tiles_calls_create_vrt(tmp_path, monkeypatch):
    src_tif = tmp_path / "source.tif"
    _write_raster(src_tif, np.full((32, 32), 1, dtype=np.int16), nodata=-9999)

    calls = {}

    def _fake_create_vrt(vrt_file, directory):
        calls["vrt_file"] = vrt_file
        calls["directory"] = directory
        vrt_file.write_text("vrt")

    monkeypatch.setattr(
        interpolate,
        "_tiles_series_from_vrt",
        lambda vrt_file, indices=None: gpd.GeoSeries(
            {"tile1": box(0, 0, 32, 32)}, crs="EPSG:28992"
        ),
    )
    monkeypatch.setattr(
        interpolate, "datastore", SimpleNamespace(processed_data_dir=tmp_path)
    )
    monkeypatch.setattr(interpolate, "create_vrt_file", _fake_create_vrt)

    vrt_file = interpolate.interpolate_ahn_tiles(
        ahn_vrt_file=src_tif,
        create_vrt=True,
        dir_name="ahn_vrt_test",
    )

    assert vrt_file == tmp_path / "ahn_vrt_test" / "ahn_vrt_test.vrt"
    assert calls["vrt_file"] == vrt_file
    assert calls["directory"] == tmp_path / "ahn_vrt_test"
    assert vrt_file.exists()
