"""Run the example against a fake pixi command, without GIS production."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("exit_code", [0, 7])
def test_example_arguments_and_failure_propagation(tmp_path, monkeypatch, exit_code):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is not installed")
    root = Path(__file__).resolve().parents[1]
    example = root / "docs/produceren/voorbeelden/afwateringseenheden_issue63.ps1"
    capture = tmp_path / "arguments.json"
    monkeypatch.setenv("BOUNDS_EXAMPLE", str(example))
    monkeypatch.setenv("BOUNDS_CAPTURE", str(capture))
    monkeypatch.setenv("BOUNDS_EXIT_CODE", str(exit_code))
    wrapper = tmp_path / "wrapper.ps1"
    wrapper.write_text(
        "function pixi {\n"
        "    @{arguments = @($args); directory = (Get-Location).Path} | "
        "ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $env:BOUNDS_CAPTURE\n"
        "    $global:LASTEXITCODE = [int]$env:BOUNDS_EXIT_CODE\n"
        "}\n"
        "[System.Threading.Thread]::CurrentThread.CurrentCulture = "
        "[System.Globalization.CultureInfo]::GetCultureInfo('nl-NL')\n"
        "& $env:BOUNDS_EXAMPLE -BrandlagenConfig '.\\map met spaties\\brandlagen.toml' "
        "-Xmin 184285.5\n"
        "exit $LASTEXITCODE\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == exit_code, result.stderr
    captured = json.loads(capture.read_text(encoding="utf-8-sig"))
    assert Path(captured["directory"]) == root
    arguments = captured["arguments"]
    assert arguments == [
        "run",
        "--environment",
        "afwateringseenheden",
        "afwateringseenheden",
        "--bounds",
        "184285.5",
        "392054",
        "185285",
        "393054",
        "--brandlagen-config",
        str(tmp_path / "map met spaties" / "brandlagen.toml"),
    ]
