from importlib import import_module
from pathlib import Path

from waterlagen.datastore import DataStore, default_data_path

datastore_module = import_module("waterlagen.datastore")


def test_default_data_path_is_repo_data_directory():
    assert default_data_path == Path(__file__).parents[1] / "data"


def test_installed_package_defaults_to_current_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(datastore_module, "repo_root", None)
    monkeypatch.chdir(tmp_path)
    for name in ("DATA_DIR", "SOURCE_DATA_DIR", "PROCESSED_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    store = DataStore(_env_file=None)
    assert store.data_dir == tmp_path / "data"
    assert store.source_data_dir == tmp_path / "data" / "source_data"
    assert store.processed_data_dir.is_dir()
    second = tmp_path / "second"
    second.mkdir()
    monkeypatch.chdir(second)
    assert DataStore(_env_file=None).data_dir == second / "data"


def test_installed_package_does_not_read_python_directory_config(tmp_path, monkeypatch):
    package = tmp_path / "Lib" / "site-packages" / "waterlagen"
    package.mkdir(parents=True)
    (tmp_path / "Lib" / ".datastore").write_text("DATA_DIR=wrong", encoding="utf-8")
    monkeypatch.setattr(datastore_module, "__file__", str(package / "datastore.py"))
    assert datastore_module._find_repo_root() is None
    monkeypatch.setattr(datastore_module, "repo_root", None)
    monkeypatch.chdir(tmp_path)
    assert datastore_module._datastore_env_files() == (tmp_path / ".datastore",)


def test_storage_accepts_windows_utf8_bom(tmp_path, monkeypatch):
    config = tmp_path / ".datastore"
    config.write_text(f"DATA_DIR={tmp_path / 'selected'}\n", encoding="utf-8-sig")
    monkeypatch.delenv("DATA_DIR", raising=False)
    store = DataStore(_env_file=config)
    assert store.data_dir == tmp_path / "selected"


def test_default_instance_can_defer_directory_creation(tmp_path):
    store = DataStore(
        data_dir=tmp_path / "unused", _env_file=None, _create_directories=False
    )
    assert not store.source_data_dir.exists()
    assert not store.processed_data_dir.exists()
    assert store.ahn_dir.is_dir()


def test_hydamo_dir_is_created_under_source_data(tmp_path):
    datastore = DataStore(data_dir=tmp_path / "data")

    assert datastore.hydamo_dir == tmp_path / "data" / "source_data" / "hydamo"
    assert datastore.hydamo_dir.is_dir()


def test_dgm1_dir_is_created_under_source_data(tmp_path):
    datastore = DataStore(data_dir=tmp_path / "data")

    assert datastore.dgm1_dir == tmp_path / "data" / "source_data" / "dgm1_nrw"
    assert datastore.dgm1_dir.is_dir()


def test_cbs_dir_is_created_under_source_data(tmp_path):
    datastore = DataStore(data_dir=tmp_path / "data")

    assert datastore.cbs_dir == tmp_path / "data" / "source_data" / "cbs"
    assert datastore.cbs_dir.is_dir()


def test_vbo_buurt_paths_are_under_processed_data(tmp_path):
    datastore = DataStore(data_dir=tmp_path / "data")

    assert datastore.vbo_buurt_dir == tmp_path / "data" / "processed_data" / "vbo_buurt"
    assert datastore.bag_vbo_path == datastore.vbo_buurt_dir / "bag_vbo.gpkg"
    assert datastore.cbs_buurt_path == datastore.vbo_buurt_dir / "cbs_buurt.gpkg"
    assert datastore.vbo_buurt_path == datastore.bag_vbo_path
    assert (
        datastore.inwoners_path
        == tmp_path / "data" / "processed_data" / "inwoners" / "inwoners.gpkg"
    )
    assert datastore.inwoners_dir.is_dir()
    assert (
        datastore.inwoners_parquet_path
        == tmp_path / "data" / "processed_data" / "inwoners" / "inwoners.parquet"
    )
    assert (
        datastore.autos_path
        == tmp_path / "data" / "processed_data" / "autos" / "autos.gpkg"
    )
    assert datastore.autos_dir.is_dir()
    assert (
        datastore.autos_parquet_path
        == tmp_path / "data" / "processed_data" / "autos" / "autos.parquet"
    )


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
