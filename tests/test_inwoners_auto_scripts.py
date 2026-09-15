import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_script(script_name: str):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(
        script_name.removesuffix(".py"), script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("script_name", "logger_name"),
    [("inwoners.py", "inwoners"), ("auto.py", "auto")],
)
def test_scripts_prepare_shared_cbs_and_vbo_buurt_data(
    script_name,
    logger_name,
    tmp_path,
    monkeypatch,
):
    script = _load_script(script_name)
    events = []
    data_store = SimpleNamespace(
        data_dir=tmp_path / "data",
        administratieve_gebieden_dir=tmp_path / "source" / "administratieve_gebieden",
        cbs_dir=tmp_path / "source" / "cbs",
        bag_dir=tmp_path / "source" / "bag",
        bag_vbo_path=tmp_path / "processed" / "vbo_buurt" / "bag_vbo.gpkg",
        cbs_buurt_path=tmp_path / "processed" / "vbo_buurt" / "cbs_buurt.gpkg",
    )
    buurtkaart_path = data_store.administratieve_gebieden_dir / "wijkenbuurten.gpkg"

    def fake_init_logger(**kwargs):
        events.append(("init_logger", kwargs))

    def fake_download_buurtkaart(**kwargs):
        events.append(("download_buurtkaart", kwargs))
        return SimpleNamespace(target_path=buurtkaart_path)

    def fake_download_buurtgegevens(**kwargs):
        events.append(("download_buurtgegevens", kwargs))

    def fake_bouw_vbo_buurt(**kwargs):
        events.append(("bouw_vbo_buurt", kwargs))
        return SimpleNamespace(bag_vbo_path=data_store.bag_vbo_path)

    monkeypatch.setattr(script, "init_logger", fake_init_logger)
    monkeypatch.setattr(
        script, "download_wijk_buurtkaart_2025", fake_download_buurtkaart
    )
    monkeypatch.setattr(
        script, "download_buurtgegevens_2025", fake_download_buurtgegevens
    )
    monkeypatch.setattr(script, "bouw_vbo_buurt", fake_bouw_vbo_buurt)

    result = script.main(data_store=data_store)

    assert result == data_store.bag_vbo_path
    assert [event[0] for event in events] == [
        "init_logger",
        "download_buurtkaart",
        "download_buurtgegevens",
        "bouw_vbo_buurt",
    ]
    assert events[0][1] == {
        "name": logger_name,
        "debug": False,
        "log_file": data_store.data_dir / f"{logger_name}.log",
    }
    assert events[1][1] == {
        "download_dir": data_store.administratieve_gebieden_dir,
        "overwrite": False,
    }
    assert events[2][1] == {
        "download_dir": data_store.cbs_dir,
        "overwrite": False,
    }
    assert events[3][1] == {
        "bag_path": data_store.bag_dir / "bag-light.gpkg",
        "buurtkaart_path": buurtkaart_path,
        "cbs_buurtgegevens_path": data_store.cbs_dir / "buurtgegevens_2025.json",
        "bag_vbo_path": data_store.bag_vbo_path,
        "cbs_buurt_path": data_store.cbs_buurt_path,
        "overwrite": False,
    }
