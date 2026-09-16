from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.transform import from_origin
from shapely.geometry import box

from waterlagen.afwateringseenheden import (
    AfwateringseenhedenTileResult,
    SubcatchmentResult,
    WatersysteemRasters,
    calculate_afwateringseenheden_tiles,
)
from waterlagen.afwateringseenheden import tiles as tiles_module
from waterlagen.raster.tiles import Tile
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


def _write_cached_tile(
    output_dir: Path,
    *,
    width: int,
    transform: Affine,
    crs: str,
) -> None:
    tile_dir = output_dir / "100000_400000_100016_400016"
    tile_dir.mkdir(parents=True)
    subcatchments = gpd.GeoDataFrame(
        {"segment_fid": [1], "segment_id": ["segment-a"]},
        geometry=[box(100000, 400000, 100016, 400016)],
        crs=crs,
    )
    subcatchments.to_file(
        tile_dir / tiles_module.SUBCATCHMENTS_GPKG_FILENAME,
        layer=tiles_module.SUBCATCHMENTS_LAYER,
        driver="GPKG",
        index=False,
    )
    with rasterio.open(
        tile_dir / tiles_module.SUBCATCHMENTS_FILENAME,
        "w",
        driver="GTiff",
        width=width,
        height=width,
        count=1,
        dtype="int32",
        crs=crs,
        transform=transform,
    ) as destination:
        destination.write(np.ones((width, width), dtype=np.int32), 1)


@pytest.mark.parametrize(
    ("optional_fields", "expected_boundary_issue", "expected_skipped_reason"),
    [
        ((), False, None),
        ((True,), True, None),
        ((True, "no segment cells"), True, "no segment cells"),
    ],
)
def test_tile_result_preserves_positional_arguments(
    tmp_path: Path,
    optional_fields: tuple[bool | str, ...],
    expected_boundary_issue: bool,
    expected_skipped_reason: str | None,
) -> None:
    tile = Tile("000000_000000_000016_000016", 0, 0, 0, 0, 16, 16)
    subcatchments = gpd.GeoDataFrame(geometry=[], crs=settings.crs)

    result = AfwateringseenhedenTileResult(
        tile, tmp_path, None, None, subcatchments, *optional_fields
    )

    assert result.has_boundary_issue is expected_boundary_issue
    assert result.skipped_reason == expected_skipped_reason
    assert result.calculation_buffer_m == 0.0


@pytest.mark.parametrize(
    ("tile_buffer_m", "resolution_m", "cached_resolution_m"),
    [
        (0.0, 2.0, 2.0),
        (4.0, 2.0, 2.0),
        (1.3, 0.1, 0.1),
        (1.3, 0.1, 0.10000000000000002),
    ],
)
def test_calculate_tiles_reuses_integer_and_fractional_cached_grids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tile_buffer_m: float,
    resolution_m: float,
    cached_resolution_m: float,
) -> None:
    output_dir = tmp_path / "tiles"
    _write_cached_tile(
        output_dir,
        width=round((16 + 2 * tile_buffer_m) / resolution_m),
        transform=from_origin(
            100000 - tile_buffer_m,
            400016 + tile_buffer_m,
            cached_resolution_m,
            cached_resolution_m,
        ),
        crs=settings.crs,
    )

    def fail_prepare(*args, **kwargs) -> WatersysteemRasters:
        pytest.fail("A matching cached tile should not be recalculated")

    monkeypatch.setattr(tiles_module, "prepare_watersysteem_rasters", fail_prepare)

    result = calculate_afwateringseenheden_tiles(
        box(100000, 400000, 100016, 400016),
        burn_depth_m=1,
        output_dir=output_dir,
        tile_size_m=16,
        tile_buffer_m=tile_buffer_m,
        resolution_m=resolution_m,
    )

    assert result.tile_results[0].subcatchments is None
    assert result.tile_results[0].calculation_buffer_m == pytest.approx(tile_buffer_m)
    assert result.merged_subcatchments.geometry.iloc[0].equals(
        box(100000, 400000, 100016, 400016)
    )


@pytest.mark.parametrize("mismatch", ["resolution", "buffer", "crs"])
def test_calculate_tiles_rejects_mismatched_cached_grids(
    tmp_path: Path, mismatch: str
) -> None:
    output_dir = tmp_path / "tiles"
    transform = from_origin(99998.7, 400017.3, 0.1, 0.1)
    crs = settings.crs
    expected_error = "CRS or resolution differs"
    if mismatch == "resolution":
        transform = from_origin(99998.7, 400017.3, 0.2, 0.2)
    elif mismatch == "buffer":
        transform = from_origin(99998.8, 400017.3, 0.1, 0.1)
        expected_error = "inconsistent buffer"
    else:
        crs = "EPSG:25832"
    _write_cached_tile(output_dir, width=186, transform=transform, crs=crs)

    with pytest.raises(ValueError, match=expected_error):
        calculate_afwateringseenheden_tiles(
            box(100000, 400000, 100016, 400016),
            burn_depth_m=1,
            output_dir=output_dir,
            tile_size_m=16,
            tile_buffer_m=1.3,
            resolution_m=0.1,
        )


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


def test_calculate_tiles_reports_boundary_issues_without_recalculation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared_bounds = []
    calculation_count = 0

    def fake_prepare(ruimtelijk_vierkant, **kwargs) -> WatersysteemRasters:
        prepared_bounds.append(ruimtelijk_vierkant.bounds)
        return _fake_rasters(Path(kwargs["output_dir"]))

    def fake_calculate(rasters: WatersysteemRasters, **kwargs) -> SubcatchmentResult:
        nonlocal calculation_count
        calculation_count += 1
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

    assert prepared_bounds == [(-100.0, -100.0, 1100.0, 1100.0)]
    assert calculation_count == 1
    assert result.tile_results[0].calculation_buffer_m == 100
    assert result.boundary_issue_tile_ids == ("000000_000000_001000_001000",)
    assert result.tile_results[0].has_boundary_issue
    assert result.tile_results[0].usable_subcatchments.empty


@pytest.mark.parametrize(
    ("options", "error", "message"),
    [
        ({"workers": True}, TypeError, "workers must be an integer"),
        ({"workers": 0}, ValueError, "workers must be at least 1"),
        ({"random_seed": True}, TypeError, "random_seed must be an integer"),
        ({"random_seed": 0}, ValueError, "random_seed must be positive"),
    ],
)
def test_calculate_tiles_rejects_invalid_worker_settings(options, error, message):
    with pytest.raises(error, match=message):
        calculate_afwateringseenheden_tiles(
            box(0, 0, 16, 16), burn_depth_m=1, **options
        )


def test_parallel_calculation_requires_existing_sources(tmp_path: Path) -> None:
    missing = tmp_path / "missing.vrt"
    with pytest.raises(FileNotFoundError) as error:
        calculate_afwateringseenheden_tiles(
            box(0, 0, 16, 16),
            burn_depth_m=1,
            ahn_vrt_path=missing,
            output_dir=tmp_path / "tiles",
            workers=2,
        )
    assert error.value.args == (missing,)


def test_cached_tile_requires_raster_metadata(tmp_path: Path) -> None:
    output_dir = tmp_path / "tiles"
    _write_cached_tile(
        output_dir,
        width=12,
        transform=from_origin(99996, 400020, 2, 2),
        crs=settings.crs,
    )
    raster = next(output_dir.glob("*/subcatchments.tif"))
    raster.unlink()
    with pytest.raises(FileNotFoundError, match="Cannot verify cached tile buffer"):
        calculate_afwateringseenheden_tiles(
            box(100000, 400000, 100016, 400016),
            burn_depth_m=1,
            output_dir=output_dir,
            tile_size_m=16,
        )
