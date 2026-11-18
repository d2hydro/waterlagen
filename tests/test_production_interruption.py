"""An interrupted DEM run can resume without admitting concurrent writers."""

import json
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from waterlagen._production import production_run, validate_run_target
from waterlagen._run_lock import run_is_locked


_CHILD_RUN = """
import sys
from pathlib import Path

from waterlagen._production import production_run

root = Path(sys.argv[1])
with production_run(
    root, "dem", "waterschap_12", run_id="interruption",
    resume="--resume" in sys.argv, parameters={"building_offset_m": 0.05}
) as run:
    checkpoint = run.path / "checkpoint.bin"
    if not checkpoint.exists():
        checkpoint.write_bytes(b"completed work")
    (root / "ready").touch()
    sys.stdin.readline()
"""


@contextmanager
def _dem_process(root: Path, *, resume: bool = False):
    """Keep a real producer alive until the test closes it."""
    ready = root / "ready"
    ready.unlink(missing_ok=True)
    log_path = root / "child.log"
    command = [sys.executable, "-c", _CHILD_RUN, str(root)]
    if resume:
        command.append("--resume")
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.monotonic() + 15
            while not ready.exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail(log_path.read_text(encoding="utf-8"))
                time.sleep(0.02)
            yield process
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            process.stdin.close()


@pytest.fixture
def active_dem_process(tmp_path):
    with _dem_process(tmp_path) as process:
        yield process


def _run_path(root: Path) -> Path:
    return root / "dem" / "waterschap_12" / "interruption"


@pytest.mark.parametrize(
    "mode, label", [("resume", "Hervatten"), ("overwrite", "Overschrijven")]
)
def test_dem_reports_mode_after_process_is_killed(
    tmp_path, active_dem_process, caplog, mode, label
):
    active_dem_process.kill()
    active_dem_process.wait(timeout=10)

    with (
        caplog.at_level("INFO"),
        production_run(
            tmp_path,
            "dem",
            "waterschap_12",
            run_id="interruption",
            resume=mode == "resume",
            overwrite=mode == "overwrite",
            parameters={"building_offset_m": 0.05},
        ) as run,
    ):
        assert run.metadata["mode"] == mode

    assert "Runmap opnieuw vergrendeld na onderbreking" in caplog.text
    assert f"Productiemodus: {label}" in caplog.text
    assert "Onderbroken run hervatten" not in caplog.text


def test_dem_can_resume_after_process_is_killed(tmp_path, active_dem_process):
    path = _run_path(tmp_path)
    active_dem_process.kill()
    active_dem_process.wait(timeout=10)
    assert json.loads((path / "run.json").read_text())["status"] == "running"

    validate_run_target(
        tmp_path,
        "dem",
        "waterschap_12",
        "interruption",
        resume=True,
        overwrite=False,
    )
    with production_run(
        tmp_path,
        "dem",
        "waterschap_12",
        run_id="interruption",
        resume=True,
        parameters={"building_offset_m": 0.05},
    ) as run:
        assert run.metadata["mode"] == "resume"
        assert (run.path / "checkpoint.bin").read_bytes() == b"completed work"

    assert json.loads((path / "run.json").read_text())["status"] == "complete"
    assert (path / "checkpoint.bin").read_bytes() == b"completed work"


def test_active_dem_process_cannot_be_resumed(tmp_path, active_dem_process):
    path = _run_path(tmp_path)
    metadata_before = (path / "run.json").read_bytes()

    with pytest.raises(ValueError, match="vergrendeld"):
        validate_run_target(
            tmp_path,
            "dem",
            "waterschap_12",
            "interruption",
            resume=True,
            overwrite=False,
        )
    with (
        pytest.raises(ValueError, match="vergrendeld"),
        production_run(
            tmp_path,
            "dem",
            "waterschap_12",
            run_id="interruption",
            resume=True,
            parameters={"building_offset_m": 0.05},
        ),
    ):
        pytest.fail("A second producer acquired the active run")

    assert active_dem_process.poll() is None
    assert (path / "run.json").read_bytes() == metadata_before
    assert (path / "checkpoint.bin").read_bytes() == b"completed work"


def test_interrupted_dem_rejects_changed_parameters(tmp_path, active_dem_process):
    path = _run_path(tmp_path)
    active_dem_process.kill()
    active_dem_process.wait(timeout=10)
    metadata_before = (path / "run.json").read_bytes()

    with (
        pytest.raises(ValueError, match="andere instellingen"),
        production_run(
            tmp_path,
            "dem",
            "waterschap_12",
            run_id="interruption",
            resume=True,
            parameters={"building_offset_m": 0.1},
        ),
    ):
        pytest.fail("An interrupted run accepted changed parameters")

    assert (path / "run.json").read_bytes() == metadata_before
    assert (path / "checkpoint.bin").read_bytes() == b"completed work"


def test_dem_can_be_killed_and_resumed_repeatedly(tmp_path):
    path = _run_path(tmp_path)
    for cycle in range(2):
        with _dem_process(tmp_path, resume=cycle > 0) as process:
            metadata = json.loads((path / "run.json").read_text())
            assert metadata["mode"] == ("new" if cycle == 0 else "resume")
            assert run_is_locked(path)
            checkpoint = path / "checkpoint.bin"
            if cycle == 0:
                checkpoint_mtime = checkpoint.stat().st_mtime_ns
            assert checkpoint.stat().st_mtime_ns == checkpoint_mtime
            assert checkpoint.read_bytes() == b"completed work"
            process.kill()
            process.wait(timeout=10)
        assert not run_is_locked(path)
        validate_run_target(
            tmp_path,
            "dem",
            "waterschap_12",
            "interruption",
            resume=True,
            overwrite=False,
        )

    with production_run(
        tmp_path,
        "dem",
        "waterschap_12",
        run_id="interruption",
        resume=True,
        parameters={"building_offset_m": 0.05},
    ):
        assert checkpoint.stat().st_mtime_ns == checkpoint_mtime
        assert checkpoint.read_bytes() == b"completed work"
    assert json.loads((path / "run.json").read_text())["status"] == "complete"


@pytest.mark.parametrize("marker_content", [b"", b"unknown lock format\n"])
@pytest.mark.parametrize("with_guard", [False, True])
def test_legacy_lock_is_preserved(tmp_path, marker_content, with_guard):
    with production_run(
        tmp_path,
        "dem",
        "waterschap_12",
        run_id="interruption",
        parameters={"building_offset_m": 0.05},
    ) as run:
        pass
    guard = run.path / ".run.guard"
    if not with_guard:
        guard.unlink()
    marker = run.path / ".run.lock"
    marker.write_bytes(marker_content)
    metadata_before = (run.path / "run.json").read_bytes()

    assert run_is_locked(run.path)
    assert guard.exists() == with_guard
    with (
        pytest.raises(ValueError, match="oud slotbestand"),
        production_run(
            tmp_path,
            "dem",
            "waterschap_12",
            run_id="interruption",
            resume=True,
            parameters={"building_offset_m": 0.05},
        ),
    ):
        pytest.fail("An unknown lock was replaced")
    assert marker.read_bytes() == marker_content
    assert (run.path / "run.json").read_bytes() == metadata_before


@pytest.mark.parametrize("active", [False, True])
def test_lock_inspection_opens_guard_read_only(
    tmp_path, active_dem_process, monkeypatch, active
):
    path = _run_path(tmp_path)
    if not active:
        active_dem_process.kill()
        active_dem_process.wait(timeout=10)
    files_before = {
        file.name: (
            None if file.name == ".run.guard" else file.read_bytes(),
            file.stat().st_size,
            file.stat().st_mtime_ns,
        )
        for file in path.iterdir()
        if file.is_file()
    }
    original_open = Path.open
    guard_modes = []

    def read_only_open(file, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in ("w", "a", "x", "+"))
        if file.name == ".run.guard":
            guard_modes.append(mode)
        return original_open(file, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", read_only_open)
        assert run_is_locked(path) is active
    assert guard_modes == ["rb"]
    files_after = {
        file.name: (
            None if file.name == ".run.guard" else file.read_bytes(),
            file.stat().st_size,
            file.stat().st_mtime_ns,
        )
        for file in path.iterdir()
        if file.is_file()
    }
    assert files_after == files_before
