import hashlib

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from waterlagen.dem import exports
from waterlagen.raster.vrt import _run_cog_validator


@pytest.mark.parametrize(
    "scale,offset,nodata",
    [(0.01, 2.35, -9999), (1, 0, -9999), (0.1, -4.5, float("nan"))],
)
def test_float_export_decodes_heights_masks_and_compression(
    tmp_path, scale, offset, nodata
):
    source = tmp_path / "dem.tif"
    target = tmp_path / "dem_float.tif"
    values = (
        np.arange(-512, 512)
        .reshape(32, 32)
        .astype("float32" if np.isnan(nodata) else "int16")
    )
    values[0, :4] = nodata
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=32,
        height=32,
        count=1,
        dtype=values.dtype,
        nodata=nodata,
        crs=28992,
        transform=from_origin(0, 32, 1, 1),
    ) as dst:
        dst.write(values, 1)
        dst.scales, dst.offsets = (scale,), (offset,)
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    exports.create_float_dem(source, target)
    exports.validate_float_dem(source, target)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original
    with rasterio.open(target) as actual:
        assert actual.dtypes == ("float32",)
        assert actual.scales == (1.0,)
        assert actual.offsets == (0.0,)
        assert actual.units == ("m",)
        assert actual.compression.value == "ZSTD"
        assert actual.tags(ns="IMAGE_STRUCTURE")["PREDICTOR"] == "3"
        assert actual.overviews(1)
        assert np.isnan(actual.read(1)[0, :4]).all()
    _run_cog_validator(target)
    assert not list(tmp_path.glob("*.tmp.*"))
    assert not list(tmp_path.glob("*.publish.*"))


def test_failed_float_validation_keeps_existing_output(tmp_path, monkeypatch):
    source = tmp_path / "dem.tif"
    target = tmp_path / "dem_float.tif"
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=32,
        height=32,
        count=1,
        dtype="int16",
        nodata=-9999,
        crs=28992,
        transform=from_origin(0, 32, 1, 1),
    ) as dst:
        dst.write(np.ones((32, 32), dtype="int16"), 1)
    exports.create_float_dem(source, target)
    before = target.read_bytes()

    def fail(*args):
        raise ValueError("simulated float validation failure")

    monkeypatch.setattr(exports, "validate_float_dem", fail)
    with pytest.raises(ValueError, match="simulated"):
        exports.create_float_dem(source, target)
    assert target.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp.*"))
    assert not list(tmp_path.glob("*.publish.*"))
