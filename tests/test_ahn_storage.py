from tkinter import filedialog, messagebox

import pytest

from waterlagen.ahn import storage
from waterlagen.datastore import DataStore


def test_unreachable_source_allows_replacement_or_cancel(tmp_path, monkeypatch):
    monkeypatch.setenv("WATERLAGEN_INTERACTIVE_DOWNLOAD", "1")
    missing = tmp_path / "unavailable"
    monkeypatch.setattr(messagebox, "askyesnocancel", lambda *args: False)
    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: str(tmp_path))
    assert storage.reachable_source(missing, 6) == tmp_path
    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: "")
    with pytest.raises(OSError, match="geannuleerd"):
        storage.reachable_source(missing, 6)
    monkeypatch.setattr(messagebox, "askyesnocancel", lambda *args: None)
    with pytest.raises(OSError, match="geannuleerd"):
        storage.reachable_source(missing, 6)


@pytest.mark.parametrize("use_default", [True, False])
def test_local_download_choice_applies_to_this_run(tmp_path, monkeypatch, use_default):
    store = DataStore(data_dir=tmp_path)
    source = tmp_path / "shared"
    source.mkdir()
    assert storage.download_target(store, source, 6, 1) == source
    assert not storage.writable(tmp_path / "missing")
    monkeypatch.setenv("WATERLAGEN_INTERACTIVE_DOWNLOAD", "1")
    monkeypatch.setattr(storage, "writable", lambda path: path != source)
    monkeypatch.setattr(messagebox, "askyesnocancel", lambda *args: use_default)
    chosen = tmp_path / "downloads"
    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: str(chosen))
    expected = store.source_data_dir / "ahn_downloads" if use_default else chosen
    assert storage.download_target(store, source, 6, 1) == expected / "AHN6"
    assert (expected / "AHN6").is_dir()
    monkeypatch.setattr(
        messagebox, "askyesnocancel", lambda *args: pytest.fail("repeated prompt")
    )
    assert storage.download_target(store, source, 5, 1) == expected / "AHN5"
    assert list(source.iterdir()) == []


@pytest.mark.parametrize("answer", [None, False])
def test_cancel_download_leaves_profile_unmodified(tmp_path, monkeypatch, answer):
    store = DataStore(data_dir=tmp_path)
    monkeypatch.setenv("WATERLAGEN_INTERACTIVE_DOWNLOAD", "1")
    monkeypatch.setattr(storage, "writable", lambda path: False)
    monkeypatch.setattr(messagebox, "askyesnocancel", lambda *args: answer)
    monkeypatch.setattr(filedialog, "askdirectory", lambda **kwargs: "")
    with pytest.raises(OSError, match="geannuleerd"):
        storage.download_target(store, tmp_path, 6, 1)
    assert store.ahn_download_dir is None
