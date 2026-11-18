"""Het keuzevenster bewaart scripts; productie gebruikt de bestaande CLI."""

import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import pytest
from shapely.geometry import box

REPOSITORY = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "runscript_tool_tests", REPOSITORY / "tools/runscript_maken/__init__.py"
)
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
generator = importlib.import_module("runscript_tool_tests.waterlagen")
script_helpers = importlib.import_module("runscript_tool_tests.script")
generic_window = importlib.import_module("runscript_tool_tests.window")


@pytest.fixture
def options():
    return generator.RunSettings(
        tuple(generator.LAYERS), ("--waterbeheercode", "12"), "hhnk-proef"
    )


def test_saved_script_contains_only_selected_commands(tmp_path, options):
    project = tmp_path / "Aa's $map `test`"
    commands = generator._commands(options)
    script = script_helpers.build_script(commands, project)
    assert script == "\n".join(commands) + "\n"
    assert "--workers 8" in script
    assert "--resume" not in script
    assert "--refresh-sources" not in script
    assert "--waterbeheercode 12" in script
    assert "runscript_maken" not in script
    assert "--data-dir" not in script
    assert "--output-root" not in script
    assert "--offline" not in script
    assert not project.exists()


def test_preview_is_only_readable_commands(options):
    commands = generator._commands(options)
    assert commands == [
        "pixi run --locked functioneel_landgebruik --waterbeheercode 12 --run-id hhnk-proef --workers 8",
        "pixi run --locked dem --waterbeheercode 12 --run-id hhnk-proef --workers 8",
        "pixi run --locked inwoners --waterbeheercode 12 --run-id hhnk-proef",
        "pixi run --locked autos --waterbeheercode 12 --run-id hhnk-proef",
        "pixi run --locked afwateringseenheden --waterbeheercode 12 --run-id hhnk-proef --workers 8",
    ]


@pytest.mark.parametrize("mode", ["resume", "overwrite"])
def test_existing_layers_get_run_flag_and_missing_layers_start_new(
    tmp_path, monkeypatch, options, mode
):
    run = tmp_path / "dem/waterschap_12/hhnk-proef"
    run.mkdir(parents=True)
    (run / "run.json").write_text("{}")
    monkeypatch.setattr(
        generator, "DataStore", lambda: SimpleNamespace(processed_data_dir=tmp_path)
    )
    selected = replace(options, **{mode: True})
    commands = generator._window_commands(selected)
    assert len(commands) == 5
    for layer, command in zip(options.layers, commands):
        assert (f"--{mode}" in command) == (layer == "dem")


def test_incomplete_existing_folder_does_not_get_overwritten(
    tmp_path, monkeypatch, options
):
    run = tmp_path / "dem/waterschap_12/hhnk-proef"
    run.mkdir(parents=True)
    marker = run / "tegel.tif"
    marker.write_bytes(b"bestaande uitvoer")
    monkeypatch.setattr(
        generator, "DataStore", lambda: SimpleNamespace(processed_data_dir=tmp_path)
    )
    with pytest.raises(ValueError, match="geen run.json"):
        generator._window_commands(replace(options, overwrite=True))
    assert marker.read_bytes() == b"bestaande uitvoer"


def test_new_run_selection_does_not_get_existing_run_flags(
    tmp_path, monkeypatch, options
):
    monkeypatch.setattr(
        generator, "DataStore", lambda: SimpleNamespace(processed_data_dir=tmp_path)
    )
    commands = generator._window_commands(replace(options, resume=True))
    assert all(
        "--resume" not in command and "--overwrite" not in command
        for command in commands
    )


def test_old_package_does_not_generate_unsupported_polygon_commands(
    monkeypatch, options
):
    monkeypatch.delattr(generator.areas, "area_from_file")
    with pytest.raises(ValueError, match="ondersteunt --area-file nog niet"):
        generator._commands(
            replace(options, area_arguments=("--area-file", "gebied.gpkg"))
        )
    assert generator._commands(options)[0].startswith(
        "pixi run --locked functioneel_landgebruik"
    )


@pytest.mark.parametrize("option", ["resume", "refresh_sources"])
def test_preview_includes_selected_run_option(options, option):
    commands = generator._commands(replace(options, **{option: True}))
    flag = "--" + option.replace("_", "-")
    assert all(command.endswith(flag) for command in commands)


@pytest.mark.parametrize("start", [False, True])
def test_save_before_starting_commands_directly(tmp_path, monkeypatch, start):
    path = tmp_path / "Aa's $proef.ps1"
    script = "pixi run --locked inwoners --waterbeheercode 12 --run-id proef\n"
    calls = []
    process = object()
    monkeypatch.setattr(script_helpers.shutil, "which", lambda name: "powershell.exe")

    def launch(command, **kwargs):
        assert path.read_text(encoding="utf-8-sig") == script
        calls.append(command)
        assert kwargs["cwd"] == tmp_path
        assert kwargs["creationflags"] == (
            subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )
        return process

    monkeypatch.setattr(generator.subprocess, "Popen", launch)
    result = script_helpers.save_script(script, path, tmp_path, start=start)
    assert path.read_text(encoding="utf-8-sig") == script
    if start:
        assert result is process
        assert len(calls) == 1
        assert calls[0][:4] == ["powershell.exe", "-NoProfile", "-NoExit", "-Command"]
        assert script.strip() in calls[0][4]
        assert str(path) not in calls[0][4]
    else:
        assert result is None
        assert calls == []


def test_failed_save_does_not_start_production(tmp_path, monkeypatch):
    def unexpected_launch(*args, **kwargs):
        pytest.fail("Productie mag niet starten als opslaan mislukt")

    monkeypatch.setattr(generator.subprocess, "Popen", unexpected_launch)
    with pytest.raises(OSError):
        script_helpers.save_script(
            "test", tmp_path / "missing/run.ps1", tmp_path, start=True
        )
    with pytest.raises(ValueError, match=".ps1"):
        script_helpers.save_script("test", tmp_path / "run.txt", tmp_path, start=True)


def test_missing_powershell_preserves_saved_script(tmp_path, monkeypatch):
    monkeypatch.setattr(script_helpers.shutil, "which", lambda name: None)
    path = tmp_path / "run.ps1"
    with pytest.raises(OSError, match="Script opgeslagen.*PowerShell"):
        script_helpers.save_script("test", path, tmp_path, start=True)
    assert path.read_text(encoding="utf-8-sig") == "test"


@pytest.mark.parametrize(
    "changes",
    [
        {"layers": ()},
        {"layers": ("unknown",)},
        {"run_id": "../bad"},
        {"workers": 0},
        {"resume": True, "refresh_sources": True},
        {"area_arguments": ("--bounds", "0", "0", "nan", "1")},
        {"area_arguments": ("--bounds", "10", "0", "0", "1")},
        {"area_arguments": ("--area", "unknown")},
        {"area_arguments": ("--waterbeheercode", "bad")},
    ],
)
def test_invalid_choices_rejected_before_saving(tmp_path, options, changes):
    with pytest.raises(ValueError):
        script_helpers.build_script(
            generator._commands(replace(options, **changes)), tmp_path
        )


@pytest.mark.parametrize(
    ("arguments", "scope"),
    [
        (("--waterbeheercode", "38"), "waterschap_38"),
        (("--area", "alkmaar_centrum"), "alkmaar_centrum"),
        (("--bounds", "1.0", "2", "3", "4"), "1_2_3_4"),
    ],
)
def test_area_uses_existing_scope_convention(arguments, scope):
    assert generator._scope(arguments) == scope


@pytest.fixture
def production(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        generator, "DataStore", lambda: SimpleNamespace(processed_data_dir=tmp_path)
    )

    def run(command, *, cwd, check):
        calls.append(command)
        assert cwd == tmp_path
        assert not check
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(generator.subprocess, "run", run)
    return tmp_path, calls


def test_resume_starts_missing_layers_and_resumes_existing(production, options):
    root, calls = production
    existing = root / "dem/waterschap_12/hhnk-proef"
    existing.mkdir(parents=True)
    (existing / "run.json").write_text("{}")
    assert generator._start(replace(options, resume=True), root) == 0
    assert len(calls) == 5
    assert "--resume" not in calls[0]
    assert "--resume" in calls[1]
    assert all("--resume" not in call for call in calls[2:])
    for layer, command in zip(generator.LAYERS, calls):
        assert command[0] == sys.executable
        assert command[1] == str(root / "scripts" / f"{layer}.py")
        assert ("--workers" in command) == (layer in generator.WORKER_LAYERS)
        assert "--refresh-sources" not in command


@pytest.mark.parametrize("resume", [False, True])
def test_existing_run_is_not_overwritten_or_unlocked(production, options, resume):
    root, calls = production
    target = root / "dem/waterschap_12/hhnk-proef"
    target.mkdir(parents=True)
    (target / "run.json").write_text("{}")
    lock = target / ".run.lock"
    lock.touch()
    with pytest.raises(ValueError):
        generator._start(replace(options, layers=("dem",), resume=resume), root)
    assert calls == []
    assert lock.exists()


def test_refresh_is_forwarded_only_when_requested(production, options):
    root, calls = production
    generator._start(replace(options, refresh_sources=True), root)
    assert all("--refresh-sources" in call for call in calls)


def test_failure_stops_remaining_layers(production, options, monkeypatch):
    root, calls = production

    def fail(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(generator.subprocess, "run", fail)
    assert generator._start(options, root) == 7
    assert len(calls) == 1


@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.parametrize("polygon", [False, True])
def test_start_calls_pixi_directly_in_order_and_stops_on_error(
    tmp_path, monkeypatch, options, exit_code, polygon
):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is niet geïnstalleerd")
    project = tmp_path / "Aa's $gebied `proef`"
    project.mkdir()
    polygon_path = project / "Aa's $gebied `proef`.gpkg"
    if polygon:
        gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs=28992).to_file(
            polygon_path, layer="gebied"
        )
        options = replace(
            options,
            area_arguments=("--area-file", str(polygon_path), "--area-layer", "gebied"),
        )
    script = tmp_path / "productie.ps1"
    launches = []
    monkeypatch.setattr(
        script_helpers.subprocess,
        "Popen",
        lambda arguments, **kwargs: launches.append(arguments),
    )
    commands = generator._commands(options)
    script_helpers.save_script(
        script_helpers.build_script(commands), script, project, start=True
    )
    assert script.read_text(encoding="utf-8-sig").splitlines() == commands
    startup = launches[0][4]
    assert str(script) not in startup
    monkeypatch.undo()
    trace = tmp_path / "calls.json"
    harness = tmp_path / "test.ps1"
    # Vervang alleen pixi, zodat er geen productie of download start.
    harness.write_text(
        f"""$global:RunTestCalls = [System.Collections.Generic.List[object]]::new()
function pixi {{
    $global:RunTestCalls.Add(@($args | ForEach-Object {{ [string]$_ }}))
    $global:LASTEXITCODE = {exit_code}
}}
try {{
    {startup}
}} catch {{
    Write-Output $_
}} finally {{
    ConvertTo-Json -InputObject $global:RunTestCalls -Depth 4 | Set-Content -LiteralPath {script_helpers.quote(str(trace))} -Encoding UTF8
}}
""",
        encoding="utf-8-sig",
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-File", str(harness)],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    calls = json.loads(trace.read_text(encoding="utf-8-sig"))
    expected_layers = list(options.layers) if exit_code == 0 else [options.layers[0]]
    assert [call[2] for call in calls] == expected_layers, result.stdout + result.stderr
    for call in calls:
        assert call[:2] == ["run", "--locked"]
        if polygon:
            assert call[3:7] == [
                "--area-file",
                str(polygon_path),
                "--area-layer",
                "gebied",
            ]
        else:
            assert call[3:5] == ["--waterbeheercode", "12"]
        assert "runscript_maken.py" not in " ".join(call)
        assert "--resume" not in call
        assert "--refresh-sources" not in call
