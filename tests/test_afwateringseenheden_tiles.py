from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from waterlagen.afwateringseenheden import (
    SubcatchmentResult,
    WatersysteemRasters,
    calculate_afwateringseenheden_tiles,
)
from waterlagen.afwateringseenheden import tiles as tiles_module
from waterlagen.settings import settings


def _write_segment_raster(path: Path, *, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=1,
        height=1,
        count=1,
        dtype="int32",
        nodata=0,
        crs=settings.crs,
        transform=from_origin(0, 1, 1, 1),
    ) as destination:
        destination.write(np.array([[value]], dtype=np.int32), 1)


def _fake_rasters(output_dir: Path, *, segment_value: int = 1) -> WatersysteemRasters:
    rasters = WatersysteemRasters(
        dem_path=output_dir / "dem_2m.tif",
        hydroobject_segment_path=output_dir / "hydroobject_segment.tif",
    )
    _write_segment_raster(rasters.hydroobject_segment_path, value=segment_value)
    return rasters


def test_calculate_tiles_uses_buffered_tile_geometry_and_writes_merged_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared_bounds: list[tuple[float, float, float, float]] = []

    def fake_prepare(ruimtelijk_vierkant, **kwargs) -> WatersysteemRasters:
        prepared_bounds.append(ruimtelijk_vierkant.bounds)
        return _fake_rasters(Path(kwargs["output_dir"]))

    def fake_calculate(rasters: WatersysteemRasters, **kwargs) -> SubcatchmentResult:
        tile_id = rasters.dem_path.parent.name
        if tile_id.startswith("000000"):
            subcatchments = gpd.GeoDataFrame(
                {"segment_fid": [1], "segment_id": ["segment-a"]},
                geometry=[box(100, 100, 500, 500)],
                crs=settings.crs,
            )
        else:
            subcatchments = gpd.GeoDataFrame(
                {"segment_fid": [2], "segment_id": ["segment-b"]},
                geometry=[box(2100, 100, 2500, 500)],
                crs=settings.crs,
            )
        return SubcatchmentResult(
            rasters.dem_path.parent / "ldd.tif",
            rasters.dem_path.parent / "subcatchments.tif",
            rasters.dem_path.parent / "afwateringseenheden.gpkg",
            subcatchments,
        )

    monkeypatch.setattr(tiles_module, "prepare_watersysteem_rasters", fake_prepare)
    monkeypatch.setattr(tiles_module, "calculate_subcatchments", fake_calculate)

    result = calculate_afwateringseenheden_tiles(
        box(0, 0, 3000, 1000),
        burn_depth_m=100,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        output_dir=tmp_path / "tiles",
        merged_output_path=tmp_path / "afwateringseenheden.gpkg",
        tile_size_m=2000,
        tile_buffer_m=10,
        resolution_m=2,
        overwrite=True,
    )

    assert prepared_bounds == [
        (-10.0, -10.0, 2010.0, 2010.0),
        (1990.0, -10.0, 4010.0, 2010.0),
    ]
    assert len(result.tile_results) == 2
    assert len(result.merged_subcatchments) == 2
    assert result.merged_path == tmp_path / "afwateringseenheden.gpkg"
    assert result.merged_path.exists()
    assert set(result.merged_subcatchments["segment_id"]) == {
        "segment-a",
        "segment-b",
    }


def test_calculate_tiles_skips_tiles_without_segment_cells(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_prepare(ruimtelijk_vierkant, **kwargs) -> WatersysteemRasters:
        return _fake_rasters(Path(kwargs["output_dir"]), segment_value=0)

    def fail_calculate(*args, **kwargs) -> SubcatchmentResult:
        raise AssertionError("tiles without segment cells should be skipped")

    monkeypatch.setattr(tiles_module, "prepare_watersysteem_rasters", fake_prepare)
    monkeypatch.setattr(tiles_module, "calculate_subcatchments", fail_calculate)

    result = calculate_afwateringseenheden_tiles(
        box(0, 0, 1000, 1000),
        burn_depth_m=100,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        output_dir=tmp_path / "tiles",
        merged_output_path=tmp_path / "afwateringseenheden.gpkg",
        tile_size_m=1000,
        overwrite=True,
    )

    assert result.skipped_tile_ids == ("000000_000000_001000_001000",)
    assert result.tile_results[0].skipped_reason == "no hydroobject_segment cells"
    assert result.merged_path is None
    assert not (tmp_path / "afwateringseenheden.gpkg").exists()
    assert result.merged_subcatchments.empty


def test_calculate_tiles_reports_boundary_issues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_prepare(ruimtelijk_vierkant, **kwargs) -> WatersysteemRasters:
        return _fake_rasters(Path(kwargs["output_dir"]))

    def fake_calculate(rasters: WatersysteemRasters, **kwargs) -> SubcatchmentResult:
        subcatchments = gpd.GeoDataFrame(
            {"segment_fid": [1], "segment_id": ["segment-a"]},
            geometry=[box(50, 50, 1099, 200)],
            crs=settings.crs,
        )
        return SubcatchmentResult(
            rasters.dem_path.parent / "ldd.tif",
            rasters.dem_path.parent / "subcatchments.tif",
            rasters.dem_path.parent / "afwateringseenheden.gpkg",
            subcatchments,
        )

    monkeypatch.setattr(tiles_module, "prepare_watersysteem_rasters", fake_prepare)
    monkeypatch.setattr(tiles_module, "calculate_subcatchments", fake_calculate)

    result = calculate_afwateringseenheden_tiles(
        box(0, 0, 1000, 1000),
        burn_depth_m=100,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        output_dir=tmp_path / "tiles",
        tile_size_m=1000,
        tile_buffer_m=100,
        resolution_m=2,
        overwrite=True,
    )

    assert result.boundary_issue_tile_ids == ("000000_000000_001000_001000",)
    assert result.tile_results[0].has_boundary_issue
    assert result.tile_results[0].usable_subcatchments.empty
