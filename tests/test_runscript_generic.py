"""Het algemene venster werkt ook voor opdrachten zonder Waterlagen."""

import json
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest
from test_runscript_maken import REPOSITORY, generic_window, script_helpers


def test_generic_parts_work_with_only_the_standard_library(tmp_path):
    code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from runscript_maken.script import format_command, build_script, save_script
from runscript_maken.window import open_window
project = Path(sys.argv[2])
command = format_command(['python', 'rapport.py', '--jaar', '2026'])
save_script(build_script([command], project), project / 'rapport.ps1', project)
assert not any(name == 'waterlagen' or name.startswith('waterlagen.') for name in sys.modules)
print(command)
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            code,
            str(REPOSITORY / "tools"),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "python rapport.py --jaar 2026"
    saved = (tmp_path / "rapport.ps1").read_text(encoding="utf-8-sig")
    assert saved == "python rapport.py --jaar 2026\n"
    assert "waterlagen" not in saved.lower()


@pytest.mark.parametrize("start", [False, True])
def test_generic_window_reads_other_choices_and_saves_or_starts(
    tmp_path, monkeypatch, start
):
    tk = pytest.importorskip("tkinter")
    from tkinter import filedialog, messagebox, ttk

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Geen grafische omgeving beschikbaar")
    root.withdraw()
    monkeypatch.setattr(tk, "Tk", lambda: root)
    name = tk.StringVar(value="voorlopig")

    def build_form(frame):
        ttk.Label(frame, text="Rapportnaam").pack()
        ttk.Entry(frame, textvariable=name).pack()

        def read_plan():
            command = script_helpers.format_command(
                ["python", "rapport.py", "--naam", name.get()]
            )
            return script_helpers.ScriptPlan("mijn-rapport", (command,))

        return read_plan

    extension = ".bat" if sys.platform == "win32" else ".ps1"
    saved_path = tmp_path / f"mijn-rapport{extension}"

    def choose_file(**kwargs):
        assert kwargs["initialfile"] == f"mijn-rapport{extension}"
        return str(saved_path)

    monkeypatch.setattr(filedialog, "asksaveasfilename", choose_file)
    monkeypatch.setattr(script_helpers.shutil, "which", lambda name: "powershell.exe")
    errors = []
    calls = []
    monkeypatch.setattr(
        messagebox, "showerror", lambda *args, **kwargs: errors.append(args)
    )
    monkeypatch.setattr(messagebox, "showinfo", lambda *args, **kwargs: None)

    def launch(command, **kwargs):
        assert saved_path.is_file()
        calls.append(command)
        return SimpleNamespace(poll=lambda: None)

    monkeypatch.setattr(script_helpers.subprocess, "Popen", launch)

    def widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from widgets(child)

    def interact():
        name.set("Aa's rapport")
        controls = {
            str(widget.cget("text")): widget
            for widget in widgets(root)
            if "text" in widget.keys()  # noqa: SIM118 - Tk widgets zijn geen dictionaries
        }
        assert "Waterschap" not in controls
        controls["Script bekijken"].invoke()
        preview = next(
            widget for widget in widgets(root) if isinstance(widget, tk.Text)
        )
        reader = (
            script_helpers.read_batch_commands
            if sys.platform == "win32"
            else script_helpers.read_commands
        )
        assert reader(preview.get("1.0", "end")) == [
            ["python", "rapport.py", "--naam", "Aa's rapport"]
        ]
        button = controls["Opslaan en starten" if start else "Alleen opslaan"]
        button.invoke()
        assert not errors
        assert saved_path.read_text(encoding="utf-8-sig") == preview.get(
            "1.0", "end-1c"
        )
        assert len(calls) == int(start)
        assert not button.instate(["disabled"])

    monkeypatch.setattr(root, "mainloop", interact)
    try:
        generic_window.open_window(tmp_path, build_form, title="Rapport maken")
    finally:
        root.destroy()


@pytest.mark.parametrize("middle_exit_code", [0, 7])
@pytest.mark.parametrize("start", [False, True])
def test_generic_script_runs_other_programs_with_literal_arguments(
    tmp_path, monkeypatch, middle_exit_code, start
):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is niet geïnstalleerd")
    project = tmp_path / "Aa's $map `proef`"
    project.mkdir()
    helper = project / "rapport.py"
    helper.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "with Path(sys.argv[1]).open('a', encoding='utf-8') as target:\n"
        "    target.write(json.dumps({'cwd': str(Path.cwd()), 'arguments': sys.argv[3:]}) + '\\n')\n"
        "raise SystemExit(int(sys.argv[2]))\n",
        encoding="utf-8",
    )
    trace = project / "resultaat.jsonl"
    arguments = ["Aa's $waarde `test`", "; Write-Output ongewenst", "$(Get-Date)"]
    commands = [
        script_helpers.format_command(
            [sys.executable, helper, trace, str(exit_code), str(index), *arguments]
        )
        for index, exit_code in enumerate([0, middle_exit_code, 0])
    ]
    path = project / "rapport.ps1"
    launches = []
    monkeypatch.setattr(
        script_helpers.subprocess,
        "Popen",
        lambda arguments, **kwargs: launches.append((arguments, kwargs)),
    )
    script_helpers.save_script(
        script_helpers.build_script(commands, project), path, project, start=start
    )
    assert path.read_text(encoding="utf-8-sig").splitlines() == commands
    monkeypatch.undo()
    invocation = [powershell, "-NoProfile", "-NonInteractive", "-File", str(path)]
    if start:
        startup = launches[0][0][4]
        assert launches[0][1]["cwd"] == project
        assert str(path) not in startup
        # De startknop voert de commando's uit zonder het bewaarde bestand te laden.
        path.unlink()
        invocation = [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            startup + "\nexit $LASTEXITCODE",
        ]
    result = subprocess.run(
        invocation,
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (middle_exit_code if start else 0), result.stderr
    assert "CategoryInfo" not in result.stderr
    assert "FullyQualifiedErrorId" not in result.stderr
    calls = [
        json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()
    ]
    assert len(calls) == (2 if start and middle_exit_code else 3)
    for index, call in enumerate(calls):
        assert call == {"cwd": str(project), "arguments": [str(index), *arguments]}


def test_start_window_reaches_prompt_after_script_failure(tmp_path, monkeypatch):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is niet geinstalleerd")
    path = tmp_path / "Aa's $proef `test`.ps1"
    command = script_helpers.format_command(
        [sys.executable, "-c", "raise SystemExit(7)"]
    )
    calls = []
    monkeypatch.setattr(
        script_helpers.subprocess,
        "Popen",
        lambda arguments, **kwargs: calls.append(arguments),
    )
    script_helpers.save_script(
        script_helpers.build_script([command], tmp_path), path, tmp_path, start=True
    )
    arguments = calls[0]
    assert arguments[1:4] == ["-NoProfile", "-NoExit", "-Command"]
    startup = arguments[4]
    monkeypatch.undo()
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            startup + "; Write-Output 'VENSTER BLIJFT OPEN'",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "VENSTER BLIJFT OPEN" in result.stdout
    assert "CategoryInfo" not in result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-runfile")
@pytest.mark.parametrize("beside_project", [False, True])
@pytest.mark.parametrize("middle_exit_code", [0, 7])
@pytest.mark.parametrize("start", [False, True])
def test_batch_runs_independently_with_literal_arguments(
    tmp_path, monkeypatch, beside_project, middle_exit_code, start
):
    project = tmp_path / "Aa's café & 100%PATH% !proef!"
    project.mkdir()
    script_folder = project if beside_project else tmp_path / "mijn runs"
    script_folder.mkdir(exist_ok=True)
    path = script_folder / "Aa's $run %PATH% & proef.bat"
    legacy = path.with_suffix(".ps1")
    legacy.write_text("bestaand bestand", encoding="utf-8-sig")
    legacy_bytes = legacy.read_bytes()
    helper = project / "controle.py"
    helper.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "with Path('resultaat.jsonl').open('a', encoding='utf-8') as target:\n"
        "    target.write(json.dumps({'cwd': str(Path.cwd()), 'arguments': sys.argv[2:]}) + '\\n')\n"
        "raise SystemExit(int(sys.argv[1]))\n",
        encoding="utf-8",
    )
    arguments = [
        "eerste",
        f"Aa's $waarde {chr(96)}test{chr(96)}",
        'a" & echo ONGEWENST & "b',
        "C:\\pad met spatie\\",
        "%RUNSCRIPT_SENTINEL%",
        "a!b^c&d(e)|f<g>h",
        "",
    ]
    commands = [
        script_helpers.format_command([sys.executable, helper, str(code), *arguments])
        for code in [0, middle_exit_code, 0]
    ]
    content = script_helpers.build_batch_script(commands, project, path)
    launches = []
    monkeypatch.setattr(
        script_helpers.subprocess,
        "Popen",
        lambda command, **kwargs: launches.append((command, kwargs)),
    )
    script_helpers.save_script(content, path, project, start=start)
    assert legacy.read_bytes() == legacy_bytes
    assert "powershell" not in content.lower()
    assert ".ps1" not in content
    assert len(launches) == int(start)
    path.write_text(content.replace("eerste", "aangepast"), encoding="utf-8")
    parsed = script_helpers.read_batch_commands(path.read_text(encoding="utf-8"))
    assert parsed[0][3:] == ["aangepast", *arguments[1:]]
    monkeypatch.undo()
    invocation = 'cmd.exe /d /s /c ""%RUNSCRIPT_FILE%""'
    environment = {
        **os.environ,
        "RUNSCRIPT_FILE": str(path),
        "RUNSCRIPT_SENTINEL": "NIET-UITVOUWEN",
    }
    if start:
        invocation, options = launches[0]
        assert options["cwd"] == project
        assert options["creationflags"] == subprocess.CREATE_NEW_CONSOLE
        environment = options["env"]
        assert environment["RUNSCRIPT_FILE"] == str(path)
    result = subprocess.run(
        invocation,
        cwd=tmp_path,
        env=environment,
        input="\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    assert result.returncode == middle_exit_code, result.stdout + result.stderr
    records = [
        json.loads(line)
        for line in (project / "resultaat.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(records) == (2 if middle_exit_code else 3)
    for record in records:
        assert record == {
            "cwd": str(project),
            "arguments": ["aangepast", *arguments[1:]],
        }
    assert legacy.read_bytes() == legacy_bytes
