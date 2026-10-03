"""The national land-use COG keeps its palette and RAT after reopening."""

import hashlib
import shutil
from xml.etree import ElementTree as ET

import numpy as np
import pytest
import rasterio
from osgeo import gdal
from rasterio.transform import from_origin

from waterlagen.functioneel_landgebruik.landgebruikstabel import load_landuse_table
from waterlagen.functioneel_landgebruik.legenda import (
    build_colormap,
    create_landuse_cog,
    write_qgis_style,
    write_raster_attribute_table,
)
from waterlagen.raster.vrt import create_cog_file, create_vrt_file


def test_interval_style_is_not_written_as_exact_value_rat(tmp_path):
    style = tmp_path / "functioneel_landgebruik.qml"
    style.write_text(
        '<qgis><pipe><rasterrenderer type="singlebandpseudocolor"/></pipe></qgis>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unieke waarden"):
        write_raster_attribute_table(tmp_path / "functioneel_landgebruik.tif", style)


def test_national_cog_rat_survives_reopen_and_copy(tmp_path):
    table = load_landuse_table()
    source = tmp_path / "tile.tif"
    raster = tmp_path / "functioneel_landgebruik.tif"
    values = np.tile(np.array([0, 1, 37, 165], dtype="uint8"), (1024, 256))
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=1024,
        height=1024,
        count=1,
        dtype="uint8",
        crs="EPSG:28992",
        transform=from_origin(0, 1024, 0.5, 0.5),
        nodata=0,
        tiled=True,
        blockxsize=512,
        blockysize=512,
    ) as destination:
        destination.write(values, 1)
        destination.write_colormap(1, build_colormap(table))

    vrt = create_vrt_file(tmp_path / "functioneel_landgebruik.vrt", [source.parent])
    style = write_qgis_style(raster, table)
    create_landuse_cog(vrt, raster, style)
    before = hashlib.sha256(raster.read_bytes()).hexdigest()
    sidecar = write_raster_attribute_table(raster, style)
    assert sidecar.name == "functioneel_landgebruik.tif.aux.xml"
    assert hashlib.sha256(raster.read_bytes()).hexdigest() == before

    shared = tmp_path / "gedeeld"
    shared.mkdir()
    for path in (raster, style, sidecar):
        shutil.copy2(path, shared / path.name)

    labels = {
        int(item.attrib["value"]): item.attrib
        for item in ET.parse(shared / style.name).iter("paletteEntry")
    }
    with rasterio.open(shared / raster.name) as reopened:
        np.testing.assert_array_equal(reopened.read(1), values)
        assert reopened.dtypes == ("uint8",)
        assert reopened.nodata == 0
        assert reopened.crs.to_epsg() == 28992
        assert reopened.res == (0.5, 0.5)
        assert reopened.block_shapes == [(512, 512)]
        assert reopened.overviews(1)

    # Read the embedded table with PAM disabled, independently of the sidecar.
    with gdal.config_option("GDAL_PAM_ENABLED", "NO"):
        dataset = gdal.Open(str(shared / raster.name), gdal.GA_ReadOnly)
    try:
        band = dataset.GetRasterBand(1)
        rat = band.GetDefaultRAT()
        assert rat is not None
        assert rat.GetRowCount() == len(labels)
        assert [rat.GetUsageOfCol(index) for index in range(6)] == [
            gdal.GFU_MinMax,
            gdal.GFU_Name,
            gdal.GFU_Red,
            gdal.GFU_Green,
            gdal.GFU_Blue,
            gdal.GFU_Alpha,
        ]
        for row in range(rat.GetRowCount()):
            code = rat.GetValueAsInt(row, 0)
            entry = labels[code]
            assert rat.GetValueAsString(row, 1) == entry["label"]
            assert tuple(rat.GetValueAsInt(row, column) for column in range(2, 6)) == (
                int(entry["color"][1:3], 16),
                int(entry["color"][3:5], 16),
                int(entry["color"][5:7], 16),
                int(entry["alpha"]),
            )
        assert labels[37]["label"].endswith("(binnendijks)")
        assert labels[165]["label"].endswith("(buitendijks)")
    finally:
        rat = None
        band = None
        dataset = None


def test_dual_rat_upgrade_repair_and_failed_publication(tmp_path, monkeypatch):
    from waterlagen.functioneel_landgebruik import legenda
    from waterlagen.raster.vrt import validate_raster_attribute_table

    source = tmp_path / "source.tif"
    ds = gdal.GetDriverByName("GTiff").Create(str(source), 32, 32, 1)
    ds.SetGeoTransform((0, 1, 0, 32, 0, -1))
    ds.SetProjection(rasterio.crs.CRS.from_epsg(28992).to_wkt())
    ds = None
    vrt = create_vrt_file(tmp_path / "input.vrt", files=[source])
    raster = tmp_path / "landuse.tif"
    create_cog_file(vrt, raster, show_progress=False)
    style = write_qgis_style(raster, load_landuse_table())
    sidecar = write_raster_attribute_table(raster, style)
    expected = legenda._build_raster_attribute_table(style)
    with pytest.raises(ValueError, match="RAT"):
        validate_raster_attribute_table(raster, expected, embedded=True)
    create_landuse_cog(vrt, raster, style)
    validate_raster_attribute_table(raster, expected, embedded=True)
    before = raster.read_bytes()
    # A sidecar must also work on a raster with no embedded RAT (old readers).
    plain_sidecar = source.with_name(source.name + ".aux.xml")
    shutil.copyfile(sidecar, plain_sidecar)
    validate_raster_attribute_table(source, expected)
    sidecar.unlink()
    create_landuse_cog(vrt, raster, style)
    assert raster.read_bytes() == before
    assert sidecar.is_file()
    # Stale sidecar values must be regenerated, even if the embedded RAT is valid.
    tree = ET.parse(sidecar)
    tree.find(".//Row/F").text = "9999"
    tree.write(sidecar)
    create_landuse_cog(vrt, raster, style)
    shutil.copyfile(sidecar, plain_sidecar)
    validate_raster_attribute_table(source, expected)
    original_sidecar = sidecar.read_bytes()

    def fail(*args, **kwargs):
        raise RuntimeError("simulated sidecar failure")

    monkeypatch.setattr(legenda, "write_raster_attribute_table", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        create_landuse_cog(vrt, raster, style, overwrite=True)
    assert raster.read_bytes() == before
    assert sidecar.read_bytes() == original_sidecar
    assert not list(tmp_path.glob("*.publish.*"))


def test_dual_rat_requires_supported_gdal(tmp_path, monkeypatch):
    from waterlagen.functioneel_landgebruik import legenda

    monkeypatch.setattr(legenda.gdal, "VersionInfo", lambda: "3110000")
    with pytest.raises(RuntimeError, match="GDAL >= 3.12"):
        create_landuse_cog(
            tmp_path / "in.vrt", tmp_path / "out.tif", tmp_path / "out.qml"
        )
