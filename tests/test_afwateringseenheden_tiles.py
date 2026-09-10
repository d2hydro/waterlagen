from pathlib import Path
import pickle

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from waterlagen.afwateringseenheden import (
    AfwateringseenhedenTileError,
    AfwateringseenhedenTilesError,
    SubcatchmentResult,
    WatersysteemRasters,
    calculate_afwateringseenheden_tiles,
)
from waterlagen.afwateringseenheden import tiles as tiles_module
from waterlagen.settings import Settings, settings


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


class _FakeFuture:
    def __init__(self, *, result=None, exception: BaseException | None = None) -> None:
        self._result = result
        self._exception = exception

    def result(self):
        if self._exception is not None:
            raise self._exception
        return self._result


def _patch_process_pool(
    monkeypatch: pytest.MonkeyPatch,
    *,
    reverse_completed: bool = False,
):
    class FakeExecutor:
        max_workers_seen: list[int] = []
        contexts = []
        submitted_jobs = []

        def __init__(self, *, max_workers, mp_context) -> None:
            self.max_workers_seen.append(max_workers)
            self.contexts.append(mp_context)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def submit(self, function, job):
            self.submitted_jobs.append(job)
            try:
                return _FakeFuture(result=function(job))
            except Exception as exc:
                return _FakeFuture(exception=exc)

    def fake_as_completed(futures):
        completed = list(futures)
        if reverse_completed:
            completed.reverse()
        return completed

    monkeypatch.setattr(tiles_module, "ProcessPoolExecutor", FakeExecutor)
    monkeypatch.setattr(tiles_module, "as_completed", fake_as_completed)
    return FakeExecutor


def _patch_successful_tile_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_prepare(ruimtelijk_vierkant, **kwargs) -> WatersysteemRasters:
        return _fake_rasters(Path(kwargs["output_dir"]))

    def fake_calculate(rasters: WatersysteemRasters, **kwargs) -> SubcatchmentResult:
        tile_id = rasters.dem_path.parent.name
        xmin = int(tile_id.split("_")[0])
        subcatchments = gpd.GeoDataFrame(
            {"segment_fid": [xmin + 1], "segment_id": [f"segment-{xmin}"]},
            geometry=[box(xmin + 100, 100, xmin + 500, 500)],
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


def _patch_workers_setting(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv("AFWATERINGSEENHEDEN_WORKERS", raising=False)
    else:
        monkeypatch.setenv("AFWATERINGSEENHEDEN_WORKERS", value)
    monkeypatch.setattr(tiles_module, "settings", Settings(_env_file=None))


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


def test_parallel_tiles_match_serial_results_and_selected_tile_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_successful_tile_calculation(monkeypatch)

    serial = calculate_afwateringseenheden_tiles(
        box(0, 0, 2000, 1000),
        burn_depth_m=100,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        output_dir=tmp_path / "serial",
        tile_size_m=1000,
        tile_buffer_m=10,
        overwrite=True,
        workers=1,
    )

    executor = _patch_process_pool(monkeypatch, reverse_completed=True)
    parallel = calculate_afwateringseenheden_tiles(
        box(0, 0, 2000, 1000),
        burn_depth_m=100,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        output_dir=tmp_path / "parallel",
        tile_size_m=1000,
        tile_buffer_m=10,
        overwrite=True,
        workers=2,
    )

    assert executor.max_workers_seen == [2]
    assert executor.contexts[0].get_start_method() == "spawn"
    assert [result.tile.tile_id for result in parallel.tile_results] == [
        "000000_000000_001000_001000",
        "001000_000000_002000_001000",
    ]
    assert list(parallel.merged_subcatchments["segment_id"]) == list(
        serial.merged_subcatchments["segment_id"]
    )
    assert list(parallel.merged_subcatchments.geometry.to_wkb()) == list(
        serial.merged_subcatchments.geometry.to_wkb()
    )


def test_worker_count_defaults_to_one_without_environment_setting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_workers_setting(monkeypatch, None)
    _patch_successful_tile_calculation(monkeypatch)
    executor = _patch_process_pool(monkeypatch)

    assert tiles_module._resolve_worker_count(None, tile_count=10) == 1
    calculate_afwateringseenheden_tiles(
        box(0, 0, 2000, 1000),
        burn_depth_m=100,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        output_dir=tmp_path / "tiles",
        tile_size_m=1000,
        overwrite=True,
        workers=None,
    )
    assert executor.max_workers_seen == []


def test_worker_count_uses_environment_setting_when_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_workers_setting(monkeypatch, "8")
    _patch_successful_tile_calculation(monkeypatch)
    executor = _patch_process_pool(monkeypatch)

    assert tiles_module._resolve_worker_count(None, tile_count=10) == 8
    calculate_afwateringseenheden_tiles(
        box(0, 0, 8000, 1000),
        burn_depth_m=100,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        output_dir=tmp_path / "tiles",
        tile_size_m=1000,
        overwrite=True,
        workers=None,
    )
    assert executor.max_workers_seen == [8]


def test_explicit_worker_count_overrides_environment_setting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_workers_setting(monkeypatch, "8")
    _patch_successful_tile_calculation(monkeypatch)
    executor = _patch_process_pool(monkeypatch)

    assert tiles_module._resolve_worker_count(4, tile_count=10) == 4
    calculate_afwateringseenheden_tiles(
        box(0, 0, 5000, 1000),
        burn_depth_m=100,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        output_dir=tmp_path / "tiles",
        tile_size_m=1000,
        overwrite=True,
        workers=4,
    )
    assert executor.max_workers_seen == [4]


def test_explicit_single_worker_keeps_public_entrypoint_serial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_workers_setting(monkeypatch, "8")
    _patch_successful_tile_calculation(monkeypatch)
    executor = _patch_process_pool(monkeypatch)

    calculate_afwateringseenheden_tiles(
        box(0, 0, 2000, 1000),
        burn_depth_m=100,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        output_dir=tmp_path / "tiles",
        tile_size_m=1000,
        overwrite=True,
        workers=1,
    )

    assert executor.max_workers_seen == []


def test_tile_job_is_picklable_for_spawn_workers(tmp_path: Path) -> None:
    tile = tiles_module.Tile(
        tile_id="000000_000000_001000_001000",
        column=0,
        row=0,
        xmin=0,
        ymin=0,
        xmax=1000,
        ymax=1000,
    )
    job = tiles_module.AfwateringseenhedenTileJob(
        tile=tile,
        output_dir=tmp_path / tile.tile_id,
        burn_depth_m=100,
        ahn_vrt_path=None,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        data_store=tiles_module.default_datastore,
        tile_buffer_m=2000,
        resolution_m=2,
        max_fill_depth_m=50,
        overwrite=False,
        engine="pcraster",
    )

    restored = pickle.loads(pickle.dumps(job))

    assert restored == job


def test_parallel_tiles_collect_skipped_and_boundary_issue_tile_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_prepare(ruimtelijk_vierkant, **kwargs) -> WatersysteemRasters:
        output_dir = Path(kwargs["output_dir"])
        segment_value = 0 if output_dir.name.startswith("000000") else 1
        return _fake_rasters(output_dir, segment_value=segment_value)

    def fake_calculate(rasters: WatersysteemRasters, **kwargs) -> SubcatchmentResult:
        subcatchments = gpd.GeoDataFrame(
            {"segment_fid": [1], "segment_id": ["segment-a"]},
            geometry=[box(1050, 50, 2099, 200)],
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
    _patch_process_pool(monkeypatch)

    result = calculate_afwateringseenheden_tiles(
        box(0, 0, 2000, 1000),
        burn_depth_m=100,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        output_dir=tmp_path / "tiles",
        tile_size_m=1000,
        tile_buffer_m=100,
        resolution_m=2,
        overwrite=True,
        workers=2,
    )

    assert result.skipped_tile_ids == ("000000_000000_001000_001000",)
    assert result.boundary_issue_tile_ids == ("001000_000000_002000_001000",)


def test_parallel_tiles_reuse_existing_outputs_when_overwrite_is_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "tiles"
    existing_paths = [
        output_dir / tile_id / "afwateringseenheden.gpkg"
        for tile_id in (
            "000000_000000_001000_001000",
            "001000_000000_002000_001000",
        )
    ]
    for existing_path in existing_paths:
        existing_path.parent.mkdir(parents=True)
        existing_path.write_text("existing")
    existing_subcatchments = gpd.GeoDataFrame(
        {"segment_fid": [1], "segment_id": ["segment-a"]},
        geometry=[box(100, 100, 500, 500)],
        crs=settings.crs,
    )

    monkeypatch.setattr(
        tiles_module,
        "_read_existing_subcatchments",
        lambda path: existing_subcatchments if path in existing_paths else None,
    )
    monkeypatch.setattr(
        tiles_module,
        "prepare_watersysteem_rasters",
        lambda *args, **kwargs: pytest.fail("existing output must be reused"),
    )
    _patch_process_pool(monkeypatch)

    result = calculate_afwateringseenheden_tiles(
        box(0, 0, 2000, 1000),
        burn_depth_m=100,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        output_dir=output_dir,
        tile_size_m=1000,
        overwrite=False,
        workers=2,
    )

    assert result.tile_results[0].subcatchments is None
    assert list(result.tile_results[0].usable_subcatchments["segment_id"]) == [
        "segment-a"
    ]
    assert (
        result.tile_results[0]
        .usable_subcatchments.geometry.iloc[0]
        .equals(existing_subcatchments.geometry.iloc[0])
    )


def test_parallel_tile_errors_include_tile_id_and_worker_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_prepare(*args, **kwargs) -> WatersysteemRasters:
        raise RuntimeError("unavailable source")

    monkeypatch.setattr(tiles_module, "prepare_watersysteem_rasters", fail_prepare)
    _patch_process_pool(monkeypatch)

    with pytest.raises(AfwateringseenhedenTilesError) as exc:
        calculate_afwateringseenheden_tiles(
            box(0, 0, 2000, 1000),
            burn_depth_m=100,
            watersysteem_path=tmp_path / "watersysteem.gpkg",
            output_dir=tmp_path / "tiles",
            tile_size_m=1000,
            overwrite=True,
            workers=2,
        )

    tile_id = "000000_000000_001000_001000"
    error = exc.value.failures[tile_id]
    assert isinstance(error, AfwateringseenhedenTileError)
    assert error.tile_id == tile_id
    assert "RuntimeError: unavailable source" in error.traceback_text
    assert tile_id in str(exc.value)


def test_parallel_tiles_reject_duplicate_output_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tile = tiles_module.Tile(
        tile_id="000000_000000_001000_001000",
        column=0,
        row=0,
        xmin=0,
        ymin=0,
        xmax=1000,
        ymax=1000,
    )
    monkeypatch.setattr(
        tiles_module, "_tiles_for_gebied", lambda *args, **kwargs: (tile, tile)
    )

    with pytest.raises(ValueError, match="unique tile IDs"):
        calculate_afwateringseenheden_tiles(
            box(0, 0, 1000, 1000),
            burn_depth_m=100,
            watersysteem_path=tmp_path / "watersysteem.gpkg",
            output_dir=tmp_path / "tiles",
            overwrite=True,
            workers=2,
        )


def test_parallel_tiles_cap_workers_to_selected_tile_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_successful_tile_calculation(monkeypatch)
    executor = _patch_process_pool(monkeypatch)

    calculate_afwateringseenheden_tiles(
        box(0, 0, 2000, 1000),
        burn_depth_m=100,
        watersysteem_path=tmp_path / "watersysteem.gpkg",
        output_dir=tmp_path / "tiles",
        tile_size_m=1000,
        overwrite=True,
        workers=20,
    )

    assert executor.max_workers_seen == [2]


@pytest.mark.parametrize("workers", [0, -1, True])
def test_calculate_tiles_rejects_invalid_worker_count(
    tmp_path: Path,
    workers: int,
) -> None:
    with pytest.raises((TypeError, ValueError), match="workers"):
        calculate_afwateringseenheden_tiles(
            box(0, 0, 1000, 1000),
            burn_depth_m=100,
            watersysteem_path=tmp_path / "watersysteem.gpkg",
            output_dir=tmp_path / "tiles",
            tile_size_m=1000,
            workers=workers,
        )
