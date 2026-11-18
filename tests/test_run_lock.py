"""Process locks preserve ownership during recovery and inspection."""

import errno
import os
from pathlib import Path

import pytest

from waterlagen._run_lock import production_lock, run_is_locked


def test_marker_removed_during_claim_is_created_again(tmp_path, monkeypatch):
    marker = tmp_path / ".run.lock"
    marker.touch()
    original_read = Path.read_bytes
    removed = False

    def read_after_previous_run_finishes(path):
        nonlocal removed
        if path == marker and not removed:
            removed = True
            marker.unlink()
            raise FileNotFoundError(marker)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_after_previous_run_finishes)

    with production_lock(tmp_path):
        assert removed
        assert marker.is_file()
        assert marker.read_bytes()
        # An older producer must also see that this run is occupied.
        with pytest.raises(FileExistsError), marker.open("xb"):
            pytest.fail("An older producer could start concurrently")

    assert not marker.exists()


def test_nonempty_guard_uses_same_lock_for_writer_and_reader(tmp_path):
    guard = tmp_path / ".run.guard"
    guard.write_bytes(b"existing guard contents")

    with production_lock(tmp_path):
        assert run_is_locked(tmp_path)
        with pytest.raises(ValueError, match="vergrendeld"), production_lock(tmp_path):
            pytest.fail("A second producer acquired a different guard region")

    assert not run_is_locked(tmp_path)
    assert guard.read_bytes() == b"existing guard contents"


@pytest.mark.parametrize("operation", ["produce", "inspect"])
def test_guard_io_error_is_not_reported_as_busy(tmp_path, monkeypatch, operation):
    (tmp_path / ".run.guard").touch()

    def fail_lock(*args):
        raise OSError(errno.EIO, "Guard could not be read")

    if os.name == "nt":
        import msvcrt

        monkeypatch.setattr(msvcrt, "locking", fail_lock)
    else:
        import fcntl

        monkeypatch.setattr(fcntl, "flock", fail_lock)

    with pytest.raises(OSError, match="Guard could not be read") as error:
        if operation == "inspect":
            run_is_locked(tmp_path)
        else:
            with production_lock(tmp_path):
                pytest.fail("Production started after a lock I/O error")

    assert error.value.errno == errno.EIO
    assert not (tmp_path / ".run.lock").exists()
