import hashlib
import xml.etree.ElementTree as ET

import numpy as np
import pytest
import rasterio
from osgeo import gdal
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


@pytest.mark.parametrize(
    "scale,unit,crs,message",
    [
        (None, "m", 7415, "expected height scale"),
        (0, "m", 7415, "positive scale"),
        (-0.01, "m", 7415, "positive scale"),
        (float("nan"), "m", 7415, "positive scale"),
        (0.01, None, 7415, "unit 'm'"),
        (0.01, "cm", 7415, "unit 'm'"),
        (0.01, "m NAP", 7415, "unit 'm'"),
        (0.01, "m", 28992, "NAP height"),
    ],
)
def test_rejects_missing_or_wrong_height_metadata(tmp_path, scale, unit, crs, message):
    path = tmp_path / "dem.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=16,
        height=16,
        count=1,
        dtype="int16",
        crs=crs,
        transform=from_origin(0, 16, 1, 1),
    ) as dst:
        dst.write(np.ones((16, 16), dtype="int16"), 1)
    # VRT exposes absent metadata directly; GeoTIFF can infer scale/unit from
    # its vertical CRS keys, masking a deliberately malformed test case.
    vrt = path.with_suffix(".vrt")
    with gdal.Translate(str(vrt), str(path), format="VRT"):
        pass
    tree = ET.parse(vrt)
    band = tree.getroot().find("VRTRasterBand")
    for name, value in (("Scale", scale), ("UnitType", unit)):
        element = band.find(name)
        if element is not None:
            band.remove(element)
        if value is not None:
            ET.SubElement(band, name).text = str(value)
    tree.write(vrt)
    with pytest.raises(ValueError, match=message):
        exports._validate_dem_metadata(vrt, expected_scale=0.01)


def test_float_validation_checks_unit(tmp_path):
    source = tmp_path / "source.tif"
    target = tmp_path / "float.tif"
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=16,
        height=16,
        count=1,
        dtype="int16",
        nodata=-9999,
        crs=7415,
        transform=from_origin(0, 16, 1, 1),
    ) as dst:
        dst.write(np.ones((16, 16), dtype="int16"), 1)
        dst.scales = (0.01,)
        dst.units = ("m",)
    exports.create_float_dem(source, target)
    # Alter a VRT copy to avoid invalidating the COG's internal layout.
    invalid = tmp_path / "invalid.vrt"
    with gdal.Translate(str(invalid), str(target), format="VRT") as dataset:
        dataset.GetRasterBand(1).SetUnitType("cm")
    with pytest.raises(ValueError, match="unit 'm'"):
        exports.validate_float_dem(source, invalid)


@pytest.mark.parametrize("crs", [28992, 7415, 3857])
def test_dem_vrt_adds_nap_without_changing_horizontal_grid(tmp_path, crs):
    from pyproj import CRS

    source = tmp_path / "terrain.tif"
    target = tmp_path / "dem.vrt"
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=16,
        height=16,
        count=1,
        dtype="int16",
        nodata=-9999,
        crs=CRS.from_epsg(crs).to_2d(),
        transform=from_origin(0, 16, 1, 1),
    ) as dst:
        dst.write(np.full((16, 16), 123, dtype="int16"), 1)
        dst.units = ("m",)
        dst.scales = (0.01,)
    if crs == 7415:
        # Assign the compound CRS through a VRT, as in the production export.
        compound_source = source.with_suffix(".vrt")
        with gdal.Translate(
            str(compound_source), str(source), format="VRT", outputSRS="EPSG:7415"
        ):
            pass
        source = compound_source
    exports._create_dem_vrt(target, [source])
    exports._validate_dem_metadata(target, expected_scale=0.01)
    with rasterio.open(source) as original, rasterio.open(target) as result:
        assert CRS(original.crs).to_2d() == CRS(result.crs).to_2d()
        assert result.transform == original.transform
        assert result.nodata == original.nodata
        np.testing.assert_array_equal(result.read(1), original.read(1))
