from pathlib import Path

import pytest

from waterlagen import _filesystem


def test_replace_retries_transient_permission_errors(tmp_path, monkeypatch, caplog):
    source, target = tmp_path / "status.tmp.json", tmp_path / "status.json"
    source.write_text("new")
    target.write_text("old")
    actual = Path.replace
    attempts = []
    delays = []

    def locked_then_available(self, destination):
        attempts.append(destination)
        if len(attempts) < 3:
            raise PermissionError(13, "simulated lock", str(destination))
        return actual(self, destination)

    monkeypatch.setattr(Path, "replace", locked_then_available)
    monkeypatch.setattr(_filesystem, "sleep", delays.append)
    _filesystem.replace_file(source, target)
    assert target.read_text() == "new"
    assert delays == [1, 1]
    assert "retry 2/10" in caplog.text


def test_replace_persistent_denial_preserves_files_and_original_error(
    tmp_path, monkeypatch
):
    source, target = tmp_path / "temporary", tmp_path / "final"
    source.write_text("new")
    target.write_text("old")
    error = PermissionError(13, "simulated denial", str(target))
    attempts = []

    def locked(self, destination):
        attempts.append(destination)
        raise error

    monkeypatch.setattr(Path, "replace", locked)
    monkeypatch.setattr(_filesystem, "sleep", lambda _: None)
    with pytest.raises(PermissionError) as raised:
        _filesystem.replace_file(source, target)
    assert raised.value is error
    assert len(attempts) == 11
    assert source.read_text() == "new"
    assert target.read_text() == "old"


def test_replace_does_not_retry_unrelated_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(_filesystem, "sleep", lambda _: pytest.fail("Unexpected retry"))
    with pytest.raises(FileNotFoundError):
        _filesystem.replace_file(tmp_path / "absent", tmp_path / "target")
