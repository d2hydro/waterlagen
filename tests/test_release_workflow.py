"""Exercise the release retry loop without network access or real waiting."""

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("bash") is None, reason="Release workflow uses Bash")
@pytest.mark.parametrize(
    ("scenario", "expected_returncode", "expected_builds"),
    [("ready", 0, 1), ("delayed", 0, 2), ("unavailable", 1, 10)],
)
def test_production_bundle_retries_refresh_pypi_cache(
    tmp_path, scenario, expected_returncode, expected_builds
):
    workflow = (
        Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
    ).read_text("utf-8")
    step = workflow.split(
        "      - name: Build and lock against the published PyPI release\n", 1
    )[1].split("\n      - uses:", 1)[0]
    script = textwrap.dedent(step.split("        run: |\n", 1)[1])
    # Simulate a stale index which stays stale until its local cache is cleared.
    commands = """
        builds=0
        stale=0
        python() {
          builds=$((builds + 1))
          echo build
          if [ "$1" != tools/build_production_bundle.py ]; then
            exit 90
          fi
          if [ "$scenario" = ready ]; then
            return 0
          fi
          if [ "$builds" = 1 ]; then
            stale=1
            return 1
          fi
          if [ "$scenario" = delayed ] && [ "$stale" = 0 ]; then
            return 0
          fi
          return 1
        }
        pixi() {
          if [ "$*" != 'clean cache --pypi --yes' ]; then
            exit 91
          fi
          stale=0
          echo refresh
        }
        sleep() {
          echo "wait $1"
        }
    """
    result = subprocess.run(
        [
            shutil.which("bash"),
            "--noprofile",
            "--norc",
            "-e",
            "-o",
            "pipefail",
            "-c",
            f"scenario={scenario}\n" + textwrap.dedent(commands) + script,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected_returncode, result.stdout + result.stderr
    output = result.stdout.splitlines()
    assert output.count("build") == expected_builds
    assert output.count("refresh") == expected_builds - 1
    assert output.count("wait 30") == expected_builds - 1
