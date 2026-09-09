from importlib import import_module
from pathlib import Path

from waterlagen.datastore import DataStore, default_data_path

datastore_module = import_module("waterlagen.datastore")


def test_default_data_path_is_repo_data_directory():
    assert default_data_path == Path(__file__).parents[1] / "data"


def test_hydamo_dir_is_created_under_source_data(tmp_path):
    datastore = DataStore(data_dir=tmp_path / "data")

    assert datastore.hydamo_dir == tmp_path / "data" / "source_data" / "hydamo"
    assert datastore.hydamo_dir.is_dir()


def test_afwateringseenheden_path_is_created_under_processed_data(tmp_path):
    datastore = DataStore(data_dir=tmp_path / "data")

    assert datastore.afwateringseenheden_path == (
        tmp_path / "data" / "processed_data" / "afwateringseenheden"
    )
    assert datastore.afwateringseenheden_path.is_dir()


def test_cwd_datastore_overrides_repo_datastore(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    monkeypatch.setattr(datastore_module, "repo_root", repo_root)
    repo_datastore = repo_root / ".datastore"
    cwd_datastore = tmp_path / ".datastore"
    repo_root.mkdir()
    repo_datastore.write_text(f"DATA_DIR={tmp_path / 'repo-data'}\n", encoding="utf-8")
    cwd_datastore.write_text(f"DATA_DIR={tmp_path / 'cwd-data'}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    try:
        datastore = DataStore()
        assert datastore.data_dir == tmp_path / "cwd-data"
    finally:
        repo_datastore.unlink()


def test_repo_datastore_is_used_when_cwd_has_none(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    monkeypatch.setattr(datastore_module, "repo_root", repo_root)
    repo_datastore = repo_root / ".datastore"
    repo_root.mkdir()
    repo_datastore.write_text(f"DATA_DIR={tmp_path / 'repo-data'}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    try:
        datastore = DataStore()
        assert datastore.data_dir == tmp_path / "repo-data"
    finally:
        repo_datastore.unlink()
