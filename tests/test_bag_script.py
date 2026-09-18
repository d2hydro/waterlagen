import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def test_bag_script_import_does_not_download_and_main_reuses_input(
    tmp_path, monkeypatch
):
    import waterlagen.bag

    download = Mock(return_value=tmp_path / "bag" / "bag-light.gpkg")
    monkeypatch.setattr(waterlagen.bag, "download_bag_light", download)
    path = Path(__file__).resolve().parents[1] / "scripts/bag.py"
    spec = importlib.util.spec_from_file_location("bag_script", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    download.assert_not_called()
    monkeypatch.setattr(script, "init_logger", Mock())
    data_store = SimpleNamespace(data_dir=tmp_path, bag_dir=tmp_path / "bag")
    assert script.main(data_store) == tmp_path / "bag" / "bag-light.gpkg"
    download.assert_called_once_with(download_dir=data_store.bag_dir, overwrite=False)
