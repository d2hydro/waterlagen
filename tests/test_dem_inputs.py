import json
from types import SimpleNamespace

import geopandas as gpd
import pytest
from shapely.geometry import box

from waterlagen._production import production_run
from waterlagen.areas import Area, resolve_workers, select_area_tiles
from waterlagen.dem import inputs


def grid():
    rows = []
    for y in (510000, 515000):
        for x in (105000, 110000, 115000):
            rows.append(
                {
                    "tile_id": f"{x}_{y}",
                    "xmin": x,
                    "ymin": y,
                    "xmax": x + 5000,
                    "ymax": y + 5000,
                    "geometry": box(x, y, x + 5000, y + 5000),
                }
            )
    return gpd.GeoDataFrame(rows, crs=28992)


def test_shared_areas_and_worker_overrides():
    tiles = grid()
    assert len(select_area_tiles(tiles, Area.nederland)) == 6
    selected = select_area_tiles(tiles, Area.alkmaar)
    assert len(selected) == 4
    assert selected.total_bounds.tolist() == [105000, 510000, 115000, 520000]
    with pytest.raises(ValueError, match="2x2"):
        select_area_tiles(selected.iloc[:3], Area.alkmaar)
    assert resolve_workers(None, 4) == 4
    assert resolve_workers(2, 4) == 2
    for workers in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            resolve_workers(workers, 4)


def record(root, scope, name, created="2026-01-01T00:00:00+00:00", status="complete"):
    path = root / "functioneel_landgebruik" / scope / name
    path.mkdir(parents=True)
    (path / "run.json").write_text(json.dumps({"created": created, "status": status}))
    return path


def fake_input(path, area):
    return inputs.LanduseInput(path, select_area_tiles(grid(), area), [], 0.5)


def test_latest_uses_creation_not_folder_name_and_does_not_hide_running(tmp_path):
    old = record(tmp_path, "nederland", "zzz")
    new = record(tmp_path, "nederland", "aaa", "2026-02-01T00:00:00+00:00", "running")
    assert inputs.latest_run(old.parent) == new
    with pytest.raises(RuntimeError, match="running"):
        inputs.validate_landuse_run(new, Area.nederland, 5)


@pytest.mark.parametrize("area", list(Area))
def test_invalid_latest_produces_requested_area_and_pins_it(
    tmp_path, monkeypatch, area
):
    old = record(tmp_path, area.value, "old")
    latest = record(tmp_path, area.value, "latest", "2026-02-01T00:00:00+00:00")
    produced = []
    examined = []

    def validate(path, selected_area, context):
        examined.append(path)
        if path == latest:
            raise ValueError("missing building companions")
        return fake_input(path, selected_area)

    def produce(store, **kwargs):
        produced.append(kwargs)
        path = (
            store.processed_data_dir
            / "functioneel_landgebruik"
            / kwargs["area"].value
            / kwargs["run_id"]
        )
        path.mkdir(parents=True)
        (path / "run.json").write_text('{"status": "complete"}')

    monkeypatch.setattr(inputs, "validate_landuse_run", validate)
    monkeypatch.setattr(inputs.landuse_production, "main", produce)
    store = SimpleNamespace(processed_data_dir=tmp_path)
    with production_run(
        tmp_path, "dem", area.value, run_id="test", parameters={}
    ) as run:
        result = inputs.resolve_landuse(store, run, area, 7)
        pinned = result.path
    assert old not in examined
    assert produced[0]["area"] == area
    assert produced[0]["building_context_m"] == 7
    assert "workers" not in produced[0]  # Prerequisite uses its own setting.
    with production_run(
        tmp_path, "dem", area.value, run_id="test", parameters={}, resume=True
    ) as run:
        monkeypatch.setattr(
            inputs, "latest_run", lambda *args: pytest.fail("Rediscovery on resume")
        )
        assert inputs.resolve_landuse(store, run, area, 7).path == pinned
    assert len(produced) == 1


def test_alkmaar_prefers_local_then_reuses_national(tmp_path, monkeypatch):
    local = record(tmp_path, "alkmaar", "local")
    national = record(tmp_path, "nederland", "national")
    examined = []

    def validate(path, area, context):
        examined.append(path)
        return fake_input(path, area)

    monkeypatch.setattr(inputs, "validate_landuse_run", validate)
    monkeypatch.setattr(
        inputs.landuse_production,
        "main",
        lambda *a, **k: pytest.fail("Unexpected production"),
    )
    store = SimpleNamespace(processed_data_dir=tmp_path)
    with production_run(
        tmp_path, "dem", "alkmaar", run_id="local", parameters={}
    ) as run:
        assert inputs.resolve_landuse(store, run, Area.alkmaar, 5).path == local
    assert examined == [local]

    def invalid_local(path, area, context):
        if path == local:
            raise FileNotFoundError("missing IDs")
        return fake_input(path, area)

    monkeypatch.setattr(inputs, "validate_landuse_run", invalid_local)
    with production_run(
        tmp_path, "dem", "alkmaar", run_id="national", parameters={}
    ) as run:
        assert inputs.resolve_landuse(store, run, Area.alkmaar, 5).path == national


def test_failed_prerequisite_resumes_same_run(tmp_path, monkeypatch):
    attempts = []
    store = SimpleNamespace(processed_data_dir=tmp_path)

    def produce(store, **kwargs):
        attempts.append(kwargs)
        path = (
            store.processed_data_dir
            / "functioneel_landgebruik"
            / "alkmaar"
            / kwargs["run_id"]
        )
        path.mkdir(parents=True, exist_ok=True)
        (path / "run.json").write_text('{"status": "failed"}')
        if len(attempts) == 1:
            raise RuntimeError("interrupted")
        (path / "run.json").write_text('{"status": "complete"}')

    monkeypatch.setattr(inputs.landuse_production, "main", produce)
    monkeypatch.setattr(
        inputs, "validate_landuse_run", lambda p, a, c: fake_input(p, a)
    )
    with (
        pytest.raises(RuntimeError, match="interrupted"),
        production_run(tmp_path, "dem", "alkmaar", run_id="test", parameters={}) as run,
    ):
        inputs.resolve_landuse(store, run, Area.alkmaar, 5)
    with production_run(
        tmp_path, "dem", "alkmaar", run_id="test", parameters={}, resume=True
    ) as run:
        inputs.resolve_landuse(store, run, Area.alkmaar, 5)
    assert attempts[0]["run_id"] == attempts[1]["run_id"]
    assert attempts[1]["resume"] is True


@pytest.mark.parametrize("error", [PermissionError("denied"), RuntimeError("running")])
def test_access_and_active_run_errors_do_not_trigger_production(
    tmp_path, monkeypatch, error
):
    record(tmp_path, "nederland", "test")

    def validate(*args):
        raise error

    monkeypatch.setattr(inputs, "validate_landuse_run", validate)
    monkeypatch.setattr(
        inputs.landuse_production,
        "main",
        lambda *a, **k: pytest.fail("Unexpected production"),
    )
    with (
        production_run(
            tmp_path, "dem", "nederland", run_id="test", parameters={}
        ) as run,
        pytest.raises(type(error)),
    ):
        inputs.resolve_landuse(
            SimpleNamespace(processed_data_dir=tmp_path), run, Area.nederland, 5
        )


def test_explicit_invalid_dependency_does_not_fallback(tmp_path, monkeypatch):
    def invalid(*args):
        raise ValueError("invalid explicit run")

    monkeypatch.setattr(inputs, "validate_landuse_run", invalid)
    monkeypatch.setattr(
        inputs, "latest_run", lambda *a: pytest.fail("Unexpected discovery")
    )
    with (
        production_run(tmp_path, "dem", "alkmaar", run_id="test", parameters={}) as run,
        pytest.raises(ValueError, match="explicit"),
    ):
        inputs.resolve_landuse(
            SimpleNamespace(processed_data_dir=tmp_path),
            run,
            Area.alkmaar,
            5,
            tmp_path / "explicit",
        )
