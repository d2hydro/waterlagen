"""Het algemene venster werkt ook voor opdrachten zonder Waterlagen."""

import json
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
    assert "python rapport.py --jaar 2026" in saved
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

    saved_path = tmp_path / "mijn-rapport.ps1"

    def choose_file(**kwargs):
        assert kwargs["initialfile"] == "mijn-rapport.ps1"
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
        expected = "python rapport.py --naam 'Aa''s rapport'"
        assert preview.get("1.0", "end").strip() == expected
        button = controls["Opslaan en starten" if start else "Alleen opslaan"]
        button.invoke()
        assert not errors
        assert expected in saved_path.read_text(encoding="utf-8-sig")
        assert len(calls) == int(start)
        assert button.instate(["disabled"]) == start

    monkeypatch.setattr(root, "mainloop", interact)
    try:
        generic_window.open_window(tmp_path, build_form, title="Rapport maken")
    finally:
        root.destroy()


@pytest.mark.parametrize("middle_exit_code", [0, 7])
def test_generic_script_runs_other_programs_with_literal_arguments(
    tmp_path, middle_exit_code
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
    script_helpers.save_script(
        script_helpers.build_script(commands, project), path, project
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-File", str(path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == (middle_exit_code == 0), result.stderr
    calls = [
        json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()
    ]
    assert len(calls) == (3 if middle_exit_code == 0 else 2)
    for index, call in enumerate(calls):
        assert call == {"cwd": str(project), "arguments": [str(index), *arguments]}
