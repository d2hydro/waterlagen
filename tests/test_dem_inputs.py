import json
from types import SimpleNamespace

import geopandas as gpd
import pytest
from shapely.geometry import box

from waterlagen._production import production_run
from waterlagen._run_lock import production_lock
from waterlagen.areas import Area, area_from_bounds, resolve_workers, select_area_tiles
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
    assert len(select_area_tiles(selected.iloc[:3], Area.alkmaar)) == 3
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


def test_latest_uses_creation_not_folder_name(tmp_path):
    old = record(tmp_path, "nederland", "zzz")
    new = record(tmp_path, "nederland", "aaa", "2026-02-01T00:00:00+00:00")
    assert inputs.latest_run(old.parent) == new


@pytest.mark.parametrize(
    "status,locked",
    [("running", True), ("running", False), ("failed", False), ("complete", True)],
)
def test_latest_prefers_completed_unlocked_run(tmp_path, status, locked):
    completed = record(tmp_path, "nederland", "afgerond")
    unfinished = record(
        tmp_path, "nederland", "later-gestart", "2026-02-01T00:00:00+00:00", status
    )
    if locked:
        (unfinished / ".run.lock").touch()
    assert inputs.latest_run(completed.parent) == completed
    assert (unfinished / ".run.lock").exists() == locked


def test_active_same_area_run_still_blocks_automatic_production(tmp_path):
    path = record(tmp_path, "alkmaar", "proef", status="running")
    store = SimpleNamespace(processed_data_dir=tmp_path)
    with (
        production_lock(path),
        pytest.raises(inputs.LanduseRunBusy, match="is vergrendeld"),
    ):
        inputs.find_landuse_input(store, Area.alkmaar, 5)


def test_dem_produces_landuse_beside_interrupted_run_with_same_name(
    tmp_path, monkeypatch
):
    interrupted = record(tmp_path, "alkmaar", "proef", status="running")
    (interrupted / ".run.guard").touch()
    (interrupted / ".run.lock").write_bytes(b"waterlagen-run-lock-v2\n")
    files = {p: p.read_bytes() for p in interrupted.iterdir()}
    store = SimpleNamespace(processed_data_dir=tmp_path)
    validate = inputs.validate_landuse_run
    produced = []

    def produce(store, *, area, run_id, **kwargs):
        produced.append(record(store.processed_data_dir, area.value, run_id))

    def validate_input(path, area, context):
        if path in produced:
            return fake_input(path, area)
        return validate(path, area, context)

    monkeypatch.setattr(inputs.landuse_production, "main", produce)
    monkeypatch.setattr(inputs, "validate_landuse_run", validate_input)
    with production_run(
        tmp_path, "dem", "alkmaar", run_id="proef", parameters={}
    ) as run:
        result = inputs.resolve_landuse(store, run, Area.alkmaar, 5)

    assert produced == [result.path]
    assert result.path != interrupted
    assert run.metadata["landuse_dependency"]["created_by_dem"] is True
    assert {p: p.read_bytes() for p in interrupted.iterdir()} == files


def test_dem_reuses_completed_landuse_beside_abandoned_run(tmp_path, monkeypatch):
    completed = record(tmp_path, "alkmaar", "afgerond")
    abandoned = record(
        tmp_path, "alkmaar", "afgebroken", "2026-02-01T00:00:00+00:00", "running"
    )
    (abandoned / ".run.lock").touch()
    checked = []

    def validate(path, area, context):
        checked.append(path)
        assert path == completed
        return fake_input(path, area)

    monkeypatch.setattr(inputs, "validate_landuse_run", validate)
    monkeypatch.setattr(
        inputs.landuse_production,
        "main",
        lambda *args, **kwargs: pytest.fail("Onnodige landgebruikproductie"),
    )
    with production_run(
        tmp_path, "dem", "alkmaar", run_id="proef", parameters={}
    ) as run:
        result = inputs.resolve_landuse(
            SimpleNamespace(processed_data_dir=tmp_path), run, Area.alkmaar, 5
        )
    assert result.path == completed
    assert checked == [completed]
    assert run.metadata["landuse_dependency"] == {
        "path": str(completed.resolve()),
        "created_by_dem": False,
    }


@pytest.mark.parametrize("locked", [False, True])
def test_blocked_landuse_explains_possible_interruption_and_next_step(tmp_path, locked):
    path = record(tmp_path, "nederland", "afgebroken", status="running")
    lock = path / ".run.lock"
    if locked:
        lock.touch()
    original = (path / "run.json").read_bytes()

    with pytest.raises(inputs.LanduseRunBusy if locked else ValueError) as error:
        inputs.validate_landuse_run(path, Area.nederland, 5)

    message = str(error.value)
    assert "afgebroken" in message
    assert str(path) in message
    if locked:
        assert "is vergrendeld" in message
        assert "afgeronde run met --landuse-run" in message
    else:
        assert "is onvoltooid" in message
        assert "Hervat deze run" in message
    assert (path / "run.json").read_bytes() == original
    assert lock.exists() == locked


@pytest.mark.parametrize(
    "area", [*Area, area_from_bounds((111250, 515750, 112250, 516750))]
)
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


@pytest.mark.parametrize("locked", [True, False])
def test_automatic_search_skips_busy_other_scope(tmp_path, monkeypatch, locked):
    other = record(tmp_path, "waterschappen_12_25", "proef", status="running")
    if locked:
        (other / ".run.lock").touch()
    store = SimpleNamespace(processed_data_dir=tmp_path)
    area = Area.alkmaar
    assert inputs.find_landuse_input(store, area, 5) is None
    with pytest.raises(inputs.LanduseRunBusy if locked else ValueError):
        inputs.validate_landuse_run(other, area, 5)
    later = record(tmp_path, "waterschappen_2_12_59", "klaar")
    original = inputs.validate_landuse_run

    def validate(path, selected, context):
        if path == later:
            return fake_input(path, selected)
        return original(path, selected, context)

    monkeypatch.setattr(inputs, "validate_landuse_run", validate)
    assert inputs.find_landuse_input(store, area, 5).path == later
