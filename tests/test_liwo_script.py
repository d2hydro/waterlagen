import runpy
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin


@pytest.fixture
def script():
    return runpy.run_path(str(Path(__file__).parents[1] / "src/waterlagen/liwo.py"))


def write_raster(path, values, *, nodata=255, count=1):
    values = np.array(values, dtype="uint8")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=count,
        dtype="uint8",
        crs="EPSG:28992",
        nodata=nodata,
        transform=from_origin(100000, 450000, 25, 25),
    ) as target:
        for band in range(1, count + 1):
            target.write(values, band)
    return path


def test_polygonize_only_selected_classes_and_holes(script, tmp_path):
    path = write_raster(
        tmp_path / "raster.tif",
        [
            [1, 1, 1, 6, 6],
            [1, 2, 1, 6, 255],
            [1, 1, 1, 3, 5],
            [0, 4, 0, 6, 0],
        ],
    )
    result = script["polygonize_selected"](path, tmp_path / "output.gpkg")
    data = gpd.read_file(result)
    assert data.crs.to_epsg() == 28992
    assert set(data.klasse) == {1, 6}
    assert data.groupby("klasse").geometry.apply(
        lambda values: values.area.sum()
    ).to_dict() == {1: 8 * 625, 6: 4 * 625}
    assert set(data.omschrijving) == set(script["SELECTED_CLASSES"].values())
    assert len(data.loc[data.klasse == 1].iloc[0].geometry.interiors) == 1
    assert data.is_valid.all()


def test_diagonal_cells_stay_separate_and_empty_selection(script, tmp_path):
    path = write_raster(tmp_path / "raster.tif", [[1, 0], [0, 1]])
    target = tmp_path / "output.gpkg"
    script["polygonize_selected"](path, target)
    assert len(gpd.read_file(target)) == 2
    write_raster(path, [[0, 2], [3, 5]])
    script["polygonize_selected"](path, target)
    assert gpd.read_file(target).empty


def test_selected_value_marked_nodata_is_excluded(script, tmp_path):
    path = write_raster(tmp_path / "raster.tif", [[1, 6]], nodata=1)
    output = script["polygonize_selected"](path, tmp_path / "output.gpkg")
    assert gpd.read_file(output).klasse.tolist() == [6]


@pytest.mark.parametrize("count,values", [(3, [[1]]), (1, [[7]])])
def test_invalid_raster_preserves_output(script, tmp_path, count, values):
    path = write_raster(tmp_path / "raster.tif", values, count=count)
    output = tmp_path / "existing.gpkg"
    output.write_bytes(b"existing")
    with pytest.raises(ValueError):
        script["polygonize_selected"](path, output)
    assert output.read_bytes() == b"existing"


def test_failed_download_preserves_cached_raster(script, tmp_path, monkeypatch):
    from waterlagen._downloads import FileDownload

    target = tmp_path / "raster.tif"
    target.write_bytes(b"existing")
    temporary = write_raster(tmp_path / "temporary.tif", [[1]])
    calls = []

    def fake_download(url, path, **kwargs):
        calls.append(url)
        return FileDownload(url, temporary, temporary.stat().st_size, False)

    monkeypatch.setitem(
        script["download_raster"].__globals__, "stream_download_to_temp", fake_download
    )
    with pytest.raises(ValueError, match="extent/grid"):
        script["download_raster"](target, overwrite=True)
    assert "service=WCS" in calls[0] and "version=2.0.1" in calls[0]
    assert "GetCoverage" in calls[0] and "image%2Ftiff" in calls[0]
    assert target.read_bytes() == b"existing"
    assert not temporary.exists()


def test_cached_download_is_validated_without_network(script, tmp_path, monkeypatch):
    target = write_raster(tmp_path / "cached.tif", [[1]])

    def fail_download(*args, **kwargs):
        raise AssertionError("Network not expected")

    monkeypatch.setitem(
        script["download_raster"].__globals__, "stream_download_to_temp", fail_download
    )
    with pytest.raises(ValueError, match="extent/grid"):
        script["download_raster"](target)
