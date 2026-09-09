from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box
from test_afwateringseenheden_raster import _write_ahn_vrt, _write_watersysteem

from waterlagen.afwateringseenheden import (
    WatersysteemRasters,
    calculate_subcatchments,
    prepare_watersysteem_rasters,
)
from waterlagen.afwateringseenheden import pcraster as pcraster_module
from waterlagen.settings import settings

CRS = settings.crs


class _FakePCRaster:
    Scalar = "scalar"
    Nominal = "nominal"

    def __init__(self) -> None:
        self.clone_arguments: tuple | None = None
        self.global_options: list[str] = []
        self.ldd_arguments: tuple | None = None
        self.subcatchment_called = False

    def setclone(self, *args) -> None:
        self.clone_arguments = args

    def setglobaloption(self, option: str) -> None:
        self.global_options.append(option)

    def numpy2pcr(self, value_scale, data: np.ndarray, missing_value):
        return data

    def lddcreate(self, elevation: np.ndarray, *args) -> np.ndarray:
        self.ldd_arguments = args
        return np.full(elevation.shape, 5, dtype=np.uint8)

    def subcatchment(self, ldd: np.ndarray, water_segments: np.ndarray) -> np.ndarray:
        self.subcatchment_called = True
        return np.where(
            np.indices(ldd.shape)[1] < 2,
            1,
            2,
        ).astype(np.int32)

    def pcr2numpy(self, data: np.ndarray, missing_value: int) -> np.ndarray:
        return data


def test_polygonize_subcatchments_resolves_segment_ids_from_fids() -> None:
    data = np.array(
        [
            [0, 1, 1, pcraster_module.SUBCATCHMENTS_NODATA],
            [2, 2, 2, 2],
        ],
        dtype=np.int32,
    )

    result = pcraster_module._polygonize_subcatchments(
        data,
        transform=from_origin(0, 4, 2, 2),
        crs=CRS,
        segment_ids_by_fid={1: "primair:0001", 2: "primair:0002"},
    )

    assert result["segment_fid"].tolist() == [1, 2]
    assert result["segment_id"].tolist() == ["primair:0001", "primair:0002"]
    assert result.crs.to_epsg() == 28992


def test_polygonize_subcatchments_rejects_unknown_segment_fid() -> None:
    with pytest.raises(ValueError, match="without a matching segment_id: 3"):
        pcraster_module._polygonize_subcatchments(
            np.array([[3]], dtype=np.int32),
            transform=from_origin(0, 2, 2, 2),
            crs=CRS,
            segment_ids_by_fid={1: "primair:0001"},
        )


def test_calculate_subcatchments_writes_aligned_rasters_and_segment_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ahn_vrt_path = _write_ahn_vrt(tmp_path)
    watersysteem_path = _write_watersysteem(tmp_path / "watersysteem.gpkg")
    rasters = prepare_watersysteem_rasters(
        box(0, 0, 8, 8),
        burn_depth_m=1.5,
        ahn_vrt_path=ahn_vrt_path,
        watersysteem_path=watersysteem_path,
        output_dir=tmp_path / "rasters",
    )
    fake_pcraster = _FakePCRaster()
    monkeypatch.setattr(
        pcraster_module,
        "require_pcraster",
        lambda: fake_pcraster,
    )

    result = calculate_subcatchments(
        rasters,
        watersysteem_path=watersysteem_path,
    )

    with (
        rasterio.open(rasters.dem_path) as dem,
        rasterio.open(rasters.hydroobject_segment_path) as segments,
        rasterio.open(result.ldd_path) as ldd,
        rasterio.open(result.subcatchments_path) as subcatchments,
    ):
        assert ldd.shape == subcatchments.shape == dem.shape == segments.shape
        assert ldd.transform == subcatchments.transform == dem.transform
        assert ldd.crs == subcatchments.crs == dem.crs
        assert ldd.nodata == pcraster_module.LDD_NODATA
        assert subcatchments.nodata == pcraster_module.SUBCATCHMENTS_NODATA
        assert np.any(ldd.read(1) != pcraster_module.LDD_NODATA)
        assert np.any(subcatchments.read(1) != pcraster_module.SUBCATCHMENTS_NODATA)

    segment_ids = gpd.read_file(
        watersysteem_path,
        layer="hydroobject_segment",
        fid_as_index=True,
    )["segment_id"]
    written = gpd.read_file(
        result.afwateringseenheden_path,
        layer=pcraster_module.SUBCATCHMENTS_LAYER,
    )
    assert result.afwateringseenheden_path.parent == rasters.dem_path.parent
    assert result.afwateringseenheden_path.name == "afwateringseenheden.gpkg"
    assert pcraster_module.SUBCATCHMENTS_LAYER not in set(
        gpd.list_layers(watersysteem_path)["name"]
    )
    assert len(written) == len(result.subcatchments)
    for row in written.itertuples():
        assert row.segment_id == segment_ids.loc[row.segment_fid]
    assert fake_pcraster.clone_arguments == (4, 4, 2.0, 0.0, 8.0)
    assert fake_pcraster.global_options == ["unittrue", "lddin"]
    assert fake_pcraster.ldd_arguments == (5000.0, 1e31, 1e31, 1e31)
    assert fake_pcraster.subcatchment_called


def test_calculate_subcatchments_rejects_unknown_engine(tmp_path: Path) -> None:
    rasters = WatersysteemRasters(
        dem_path=tmp_path / "dem_2m.tif",
        hydroobject_segment_path=tmp_path / "hydroobject_segment.tif",
    )

    with pytest.raises(ValueError, match="Unsupported subcatchment engine"):
        calculate_subcatchments(rasters, engine="other")
