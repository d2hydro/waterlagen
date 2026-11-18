"""De DEM-toelichting volgt bronkeuze, hervatten en expliciete invoer."""

import importlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from waterlagen.dem import inputs
from test_runscript_maken import generator

preview = importlib.import_module("runscript_tool_tests.dem_preview")
app = importlib.import_module("runscript_tool_tests.browser_app")
OptionValue = importlib.import_module(
    "runscript_tool_tests.waterlagen_options"
).OptionValue


@pytest.fixture
def options():
    return generator.RunSettings(
        ("dem",), ("--bounds", "110100", "515100", "110900", "515900"), "test"
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    result = SimpleNamespace(processed_data_dir=tmp_path)
    monkeypatch.setattr(preview, "DataStore", lambda: result)
    return result


def recorded_run(store, scope, name, created, status="complete"):
    path = store.processed_data_dir / "functioneel_landgebruik" / scope / name
    path.mkdir(parents=True)
    (path / "run.json").write_text(json.dumps({"created": created, "status": status}))
    return path


def test_missing_landuse_announces_production_without_creating_files(store, options):
    assert preview.preview_landuse(options, "resume").state == "create"
    assert not list(store.processed_data_dir.iterdir())


def test_completed_candidate_preferred_over_newer_running_one(
    store, options, monkeypatch
):
    scope = generator._scope(options.area_arguments)
    complete = recorded_run(store, scope, "klaar", "2026-11-17T12:00:00+00:00")
    recorded_run(store, scope, "bezig", "2026-11-18T12:00:00+00:00", "running")
    checked = []

    def validate(path, area, context):
        checked.append((path, area.value, context))
        return SimpleNamespace(path=path)

    monkeypatch.setattr(inputs, "validate_landuse_run", validate)
    result = preview.preview_landuse(options, "resume")
    assert result.state == "reuse"
    assert result.path == str(complete)
    assert checked == [(complete, scope, 5.0)]


def test_invalid_coverage_falls_through_to_other_scope(store, options, monkeypatch):
    scope = generator._scope(options.area_arguments)
    wrong = recorded_run(store, scope, "onvolledig", "2026-11-17T12:00:00+00:00")
    good = recorded_run(store, "nederland", "landelijk", "2026-11-16T12:00:00+00:00")

    def validate(path, area, context):
        if path == wrong:
            raise ValueError("Missing tile")
        return SimpleNamespace(path=path)

    monkeypatch.setattr(inputs, "validate_landuse_run", validate)
    assert preview.preview_landuse(options, "resume").path == str(good)


@pytest.mark.parametrize("mode", ["resume", "overwrite"])
def test_existing_dependency_has_priority_over_refresh_and_selected_landuse(
    store, options, mode
):
    target = (
        store.processed_data_dir
        / "dem"
        / generator._scope(options.area_arguments)
        / "test"
    )
    target.mkdir(parents=True)
    dependency = str(store.processed_data_dir / "vastgelegde-bron")
    (target / "run.json").write_text(
        json.dumps({"landuse_dependency": {"path": dependency}})
    )
    result = preview.preview_landuse(
        replace(options, layers=("functioneel_landgebruik", "dem")), mode
    )
    assert result.state == "recorded"
    assert result.path == dependency


def test_refresh_announces_new_landuse(store, options):
    result = preview.preview_landuse(replace(options, refresh_sources=True), "resume")
    assert result.state == "create"
    assert "bronnen vernieuwen" in result.message


def test_landuse_selected_in_same_script_announces_execution_order(store, options):
    result = preview.preview_landuse(
        replace(options, layers=("functioneel_landgebruik", "dem")), "resume"
    )
    assert result.state == "planned"
    assert "Landgebruik draait eerst" in result.message


def test_explicit_path_and_search_distance_use_dem_validation(
    store, options, monkeypatch
):
    chosen = store.processed_data_dir / "eigen-run"
    calls = []

    def validate(path, area, context):
        calls.append((path, context))
        return SimpleNamespace(path=path)

    monkeypatch.setattr(preview, "validate_landuse_run", validate)
    options = replace(
        options,
        refresh_sources=True,
        extra_options=(
            OptionValue("dem", "landuse-run", str(chosen)),
            OptionValue("dem", "building-max-search-distance-m", "8"),
        ),
    )
    assert preview.preview_landuse(options, "resume").path == str(chosen)
    assert calls == [(chosen, 8.0)]


def test_running_candidate_is_not_announced_as_new_production(
    store, options, monkeypatch
):
    recorded_run(
        store,
        generator._scope(options.area_arguments),
        "bezig",
        "2026-11-18T12:00:00+00:00",
        "running",
    )

    def validate(*args):
        raise RuntimeError("Landgebruikrun is nog bezig")

    monkeypatch.setattr(inputs, "validate_landuse_run", validate)
    monkeypatch.setattr(app, "run_settings", lambda values: options)
    result = app.RunApplication(store.processed_data_dir, None).dispatch(
        "dem_landuse", {}
    )
    assert result["state"] == "error"
    assert "nog bezig" in result["message"]


def test_missing_boundary_does_not_download(store, options, monkeypatch):
    def resolve(area, datastore, preparation):
        assert preparation.offline
        assert not preparation.refresh
        raise FileNotFoundError("boundary")

    monkeypatch.setattr(preview, "resolve_area", resolve)
    result = preview.preview_landuse(
        replace(options, area_arguments=("--waterbeheercode", "12")), "resume"
    )
    assert result.state == "unknown"


def test_manual_selection_requires_path_but_auto_preserves_old_scripts():
    values = {
        "mode": "bounds",
        "bounds": [110100, 515100, 110900, 515900],
        "layers": ["dem"],
        "run_id": "test",
    }
    assert app.run_settings(values).layers == ("dem",)
    with pytest.raises(ValueError, match="Kies een landgebruikrun"):
        app.run_settings({**values, "dem_landuse_mode": "manual"})
