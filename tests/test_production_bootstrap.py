"""Exercise the documented one-time updater commands without network access."""

import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import urllib.request
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
PAGE = REPOSITORY / "docs/produceren/installatie.md"


def command_block(language):
    page = PAGE.read_text("utf-8")
    block = page.split(f"```{language}\n", 1)[1].split("```", 1)[0]
    return textwrap.dedent(block)


@pytest.mark.parametrize("returncode", [0, 1])
def test_linux_bootstrap_preserves_target_tag_and_interactive_input(
    tmp_path, monkeypatch, returncode
):
    command = shlex.split(command_block("bash"))
    assert command[:7] == [
        "pixi",
        "exec",
        "--spec",
        "python=3.13",
        "--",
        "python",
        "-c",
    ]
    root = tmp_path / "existing production with spaces"
    root.mkdir()
    monkeypatch.chdir(root)
    updater_source = (REPOSITORY / "tools/code_bijwerken.py").read_bytes()
    requests = []
    captured = []

    def urlopen(url, *, timeout):
        assert timeout == 60
        requests.append(url)
        if url.endswith("/latest"):
            return io.BytesIO(b'{"tag_name": "2026.11.1"}')
        assert "/download/2026.11.1/waterlagen-updater.py" in url
        return io.BytesIO(updater_source)

    def start(arguments):
        # No redirected stdin: the updater can ask the user to confirm.
        path = Path(arguments[1])
        assert path.read_bytes() == updater_source
        assert not path.is_relative_to(root)
        assert arguments[2:] == ["--project-dir", str(root), "--versie", "2026.11.1"]
        captured.append(path)
        return returncode

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(subprocess, "call", start)
    with pytest.raises(SystemExit) as stopped:
        exec(compile(command[7], str(PAGE), "exec"), {})
    assert stopped.value.code == returncode
    assert len(requests) == 2
    assert len(captured) == 1
    assert not captured[0].exists()
    assert not list(root.iterdir())


@pytest.mark.skipif(
    sys.platform != "win32" or shutil.which("powershell") is None,
    reason="Requires Windows PowerShell",
)
def test_powershell_bootstrap_uses_the_existing_folder_and_a_temporary_updater(
    tmp_path,
):
    root = tmp_path / "existing production with spaces"
    root.mkdir()
    result_path = tmp_path / "arguments.json"
    stub = r"""
function Invoke-RestMethod {
    [CmdletBinding()] param([string]$Uri)
    if (-not $Uri.EndsWith('/latest')) { throw 'unexpected release request' }
    [pscustomobject]@{tag_name='2026.11.1'}
}
function Invoke-WebRequest {
    [CmdletBinding()] param([string]$Uri, [string]$OutFile)
    if (-not $Uri.EndsWith('/download/2026.11.1/waterlagen-updater.py')) { throw 'wrong release asset' }
    [IO.File]::WriteAllText($OutFile, 'temporary updater')
}
"""
    script = tmp_path / "bootstrap-test.ps1"
    script.write_text(stub + command_block("powershell"), encoding="utf-8-sig")
    environment = os.environ.copy()
    environment["WATERLAGEN_BOOTSTRAP_RESULT"] = str(result_path)
    # Een echte opdracht behoudt '--'; een PowerShell-functiemock slikt dat token in.
    commands = tmp_path / "commands with spaces"
    commands.mkdir()
    capture = commands / "capture.py"
    capture.write_text(
        "import json, os, sys\nfrom pathlib import Path\n"
        "arguments = sys.argv[1:]\n"
        "assert Path(arguments[5]).read_text() == 'temporary updater'\n"
        "Path(os.environ['WATERLAGEN_BOOTSTRAP_RESULT']).write_text(json.dumps(arguments))\n"
    )
    (commands / "pixi.cmd").write_text(
        '@echo off\n"%WATERLAGEN_BOOTSTRAP_PYTHON%" "%WATERLAGEN_BOOTSTRAP_CAPTURE%" %*\n'
    )
    environment["WATERLAGEN_BOOTSTRAP_PYTHON"] = sys.executable
    environment["WATERLAGEN_BOOTSTRAP_CAPTURE"] = str(capture)
    environment["PATH"] = str(commands) + os.pathsep + environment["PATH"]
    result = subprocess.run(
        [
            shutil.which("powershell"),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(script),
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result_path.is_file(), result.stdout + result.stderr
    arguments = json.loads(result_path.read_text())
    assert arguments[:5] == ["exec", "--spec", "python=3.13", "--", "python"]
    updater_path = Path(arguments[5])
    assert arguments[6:] == ["--project-dir", str(root), "--versie", "2026.11.1"]
    assert not updater_path.is_relative_to(root)
    assert not updater_path.exists()
    assert not list(root.iterdir())
