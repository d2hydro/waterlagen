import os
import subprocess
import sys
from importlib import import_module
from unittest.mock import Mock

import pytest

from waterlagen import cli, datastore
from waterlagen.afwateringseenheden import production


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(import_module("waterlagen.datastore"), "repo_root", None)
    for name in ("data_dir", "source_data_dir", "processed_data_dir"):
        monkeypatch.setattr(datastore, name, getattr(datastore, name))
        monkeypatch.setenv(name.upper(), "")
        monkeypatch.delenv(name.upper())
    monkeypatch.setattr(cli, "init_logger", Mock())


def test_cli_forwards_parameters_and_storage_to_production(tmp_path, monkeypatch):
    produce = Mock(return_value=tmp_path / "result.gpkg")
    monkeypatch.setattr(production, "produce_afwateringseenheden", produce)
    monkeypatch.setenv("SOURCE_DATA_DIR", str(tmp_path / "old-source"))
    monkeypatch.setenv("PROCESSED_DATA_DIR", str(tmp_path / "old-results"))
    selected = tmp_path / "chosen data"
    assert (
        cli.main(
            [
                "afwateringseenheden",
                "--waterschap",
                "25",
                "--data-dir",
                str(selected),
                "--workers",
                "2",
                "--buffer-m",
                "500",
                "--tile-size-m",
                "5000",
                "--tile-buffer-m",
                "1000",
                "--burn-depth-m",
                "80",
                "--max-fill-depth-m",
                "40",
                "--seed",
                "7",
            ]
        )
        == 0
    )
    config = produce.call_args.args[0]
    assert config == production.ProductionConfig(
        waterbeheercode="25",
        workers=2,
        buffer_m=500,
        tile_size_m=5000,
        tile_buffer_m=1000,
        burn_depth_m=80,
        max_fill_depth_m=40,
        random_seed=7,
    )
    store = produce.call_args.kwargs["data_store"]
    assert store.data_dir == selected
    assert store.source_data_dir == selected / "source_data"
    assert store.processed_data_dir == selected / "processed_data"
    assert datastore.data_dir == selected
    assert os.environ["DATA_DIR"] == str(selected)
    assert os.environ["SOURCE_DATA_DIR"] == str(store.source_data_dir)
    assert os.environ["PROCESSED_DATA_DIR"] == str(store.processed_data_dir)
    assert not (tmp_path / "old-source").exists()


def test_cli_respects_configuration_when_data_dir_is_omitted(tmp_path, monkeypatch):
    (tmp_path / ".datastore").write_text(
        "DATA_DIR=custom\nSOURCE_DATA_DIR=downloads", encoding="utf-8"
    )
    check = Mock()
    monkeypatch.setattr(cli, "_check_installation", check)
    assert cli.main(["controleer"]) == 0
    store = check.call_args.args[0]
    assert store.data_dir == tmp_path / "custom"
    assert store.source_data_dir == tmp_path / "downloads"


@pytest.mark.parametrize(
    "option,value",
    [
        ("--workers", "0"),
        ("--workers", "abc"),
        ("--buffer-m", "-1"),
        ("--buffer-m", "nan"),
        ("--tile-size-m", "0"),
        ("--waterschap", "../38"),
        ("--seed", "0"),
        ("--max-fill-depth-m", "inf"),
    ],
)
def test_cli_rejects_invalid_arguments_before_starting(
    tmp_path, monkeypatch, option, value
):
    produce = Mock()
    monkeypatch.setattr(production, "produce_afwateringseenheden", produce)
    with pytest.raises(SystemExit) as error:
        cli.main(["afwateringseenheden", option, value])
    assert error.value.code == 2
    produce.assert_not_called()
    assert not (tmp_path / "data").exists()


def test_cli_reports_failure_with_nonzero_status(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(
        cli, "_check_installation", Mock(side_effect=RuntimeError("PCRaster ontbreekt"))
    )
    assert cli.main(["controleer", "--data-dir", str(tmp_path / "data")]) == 1
    assert "PCRaster ontbreekt" in caplog.text


def test_help_does_not_create_storage_or_load_gis(tmp_path):
    environment = os.environ.copy()
    environment["DATA_DIR"] = str(tmp_path / "unused")
    result = subprocess.run(
        [sys.executable, "-m", "waterlagen", "--help"],
        check=False,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "afwateringseenheden" in result.stdout
    assert "controleer" in result.stdout
    assert not (tmp_path / "unused").exists()
