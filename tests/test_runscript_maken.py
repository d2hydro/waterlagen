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
    "runscript_maken", REPOSITORY / "envs/runscript_maken.py"
)
generator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = generator
spec.loader.exec_module(generator)


@pytest.fixture
def options():
    return generator.RunSettings(
        tuple(generator.LAYERS), ("--waterbeheercode", "12"), "hhnk-proef"
    )


def test_script_defaults_and_literal_paths(tmp_path, options):
    project = tmp_path / "Aa's $map `test`"
    script = generator._script(options, project)
    assert "--workers 8" in script
    assert "--resume" not in script
    assert "--refresh-sources" not in script
    assert "--waterbeheercode 12" in script
    assert "runscript_maken" not in script
    assert "Aa''s $map `test`" in script
    assert "$LASTEXITCODE -ne 0" in script
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
def test_save_before_starting_exact_saved_script(tmp_path, monkeypatch, start):
    path = tmp_path / "Aa's $proef.ps1"
    script = "# Opgeslagen keuzes\nWrite-Output 'proef'\n"
    calls = []
    process = object()
    monkeypatch.setattr(generator.shutil, "which", lambda name: "powershell.exe")

    def launch(command, **kwargs):
        assert path.read_text(encoding="utf-8-sig") == script
        calls.append(command)
        assert kwargs["cwd"] == tmp_path
        assert kwargs["creationflags"] == (
            subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )
        return process

    monkeypatch.setattr(generator.subprocess, "Popen", launch)
    result = generator._save_script(script, path, tmp_path, start=start)
    assert path.read_text(encoding="utf-8-sig") == script
    if start:
        assert result is process
        assert calls == [
            ["powershell.exe", "-NoProfile", "-NoExit", "-File", str(path)]
        ]
    else:
        assert result is None
        assert calls == []


def test_failed_save_does_not_start_production(tmp_path, monkeypatch):
    def unexpected_launch(*args, **kwargs):
        pytest.fail("Productie mag niet starten als opslaan mislukt")

    monkeypatch.setattr(generator.subprocess, "Popen", unexpected_launch)
    with pytest.raises(OSError):
        generator._save_script(
            "test", tmp_path / "missing/run.ps1", tmp_path, start=True
        )
    with pytest.raises(ValueError, match=".ps1"):
        generator._save_script("test", tmp_path / "run.txt", tmp_path, start=True)


def test_missing_powershell_preserves_saved_script(tmp_path, monkeypatch):
    monkeypatch.setattr(generator.shutil, "which", lambda name: None)
    path = tmp_path / "run.ps1"
    with pytest.raises(OSError, match="Script opgeslagen.*PowerShell"):
        generator._save_script("test", path, tmp_path, start=True)
    assert path.read_text(encoding="utf-8-sig") == "test"


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("selection", ["Heel Nederland", "Polygoonbestand"])
def test_window_saves_and_starts_selection_or_cancels(
    tmp_path, monkeypatch, cancel, selection
):
    tk = pytest.importorskip("tkinter")
    from tkinter import filedialog, messagebox

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Geen grafische omgeving beschikbaar")
    root.withdraw()
    monkeypatch.setattr(tk, "Tk", lambda: root)
    path = tmp_path / "nederland.ps1"
    monkeypatch.setattr(
        filedialog, "asksaveasfilename", lambda **kwargs: "" if cancel else str(path)
    )
    monkeypatch.setattr(generator.shutil, "which", lambda name: "powershell.exe")
    polygon_path = tmp_path / "gebied.gpkg"
    if selection == "Polygoonbestand":
        gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs=28992).to_file(
            polygon_path, layer="gebied"
        )
        monkeypatch.setattr(
            filedialog, "askopenfilename", lambda **kwargs: str(polygon_path)
        )
    expected_argument = (
        "--area nederland" if selection == "Heel Nederland" else "--area-file"
    )
    calls = []
    errors = []
    monkeypatch.setattr(
        messagebox, "showerror", lambda *args, **kwargs: errors.append(args)
    )

    def launch(command, **kwargs):
        calls.append(command)
        assert path.is_file()
        return SimpleNamespace(poll=lambda: None)

    monkeypatch.setattr(generator.subprocess, "Popen", launch)

    def widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from widgets(child)

    def interact():
        controls = {
            str(widget.cget("text")): widget
            for widget in widgets(root)
            if "text" in widget.keys()  # noqa: SIM118 - Tk widgets zijn geen dictionaries
        }
        assert "Voorbeeldgebied" not in controls
        controls[selection].invoke()
        if selection == "Polygoonbestand":
            controls["Bestand kiezen"].invoke()
        controls["Script bekijken"].invoke()
        preview_text = next(
            widget for widget in widgets(root) if isinstance(widget, tk.Text)
        )
        preview_lines = preview_text.get("1.0", "end").strip().splitlines()
        assert len(preview_lines) == 5
        assert all(line.startswith("pixi run --locked ") for line in preview_lines)
        assert all(expected_argument in line for line in preview_lines)
        assert "runscript_maken" not in "\n".join(preview_lines)
        button = controls["Opslaan en starten"]
        button.invoke()
        assert not errors
        if cancel:
            assert not path.exists()
            assert calls == []
            assert not button.instate(["disabled"])
        else:
            assert len(calls) == 1
            assert expected_argument in path.read_text(encoding="utf-8-sig")
            assert button.instate(["disabled"])

    monkeypatch.setattr(root, "mainloop", interact)
    try:
        generator._window(tmp_path)
    finally:
        root.destroy()


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
        generator._script(replace(options, **changes), tmp_path)


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
def test_saved_powershell_runs_layers_in_order_and_stops_on_error(
    tmp_path, options, exit_code, polygon
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
    script.write_text(generator._script(options, project), encoding="utf-8-sig")
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
    & {generator._ps_quote(str(script))}
}} catch {{
    Write-Output $_
}} finally {{
    ConvertTo-Json -InputObject $global:RunTestCalls -Depth 4 | Set-Content -LiteralPath {generator._ps_quote(str(trace))} -Encoding UTF8
}}
""",
        encoding="utf-8-sig",
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-File", str(harness)],
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
