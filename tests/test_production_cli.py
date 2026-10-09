import importlib.util
import logging
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from unittest.mock import Mock

import geopandas as gpd
import pytest
from shapely.geometry import box

from waterlagen._cli import production_parser, run_cli
from waterlagen._run_logging import executor_logging, production_logging, run_log
from waterlagen._sources import SourcePreparation, prepare_cached, source_options
from waterlagen.areas import NAMED_AREAS, ProductionArea, area_name, select_area_tiles
from waterlagen.logger import get_logger, tile_logging

PRODUCTS = [
    "autos",
    "inwoners",
    "afwateringseenheden",
    "functioneel_landgebruik",
    "dem",
]


@pytest.mark.parametrize("product", PRODUCTS)
def test_help_is_shared_and_does_not_start_production(product, monkeypatch, capsys):
    path = Path(__file__).parents[1] / "scripts" / f"{product}.py"
    spec = importlib.util.spec_from_file_location(product, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    main = Mock()
    monkeypatch.setattr(module, "main", main)
    monkeypatch.setattr("sys.argv", [str(path), "--help"])
    with pytest.raises(SystemExit) as result:
        module.cli()
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert all(
        option in help_text
        for option in (
            "--area",
            "--waterbeheercode",
            "--data-dir",
            "--output-root",
            "--refresh-sources",
            "--offline",
            "--resume",
            "--overwrite",
            "--run-id",
            "--debug",
        )
    )
    main.assert_not_called()


@pytest.mark.parametrize(
    "arguments",
    [
        ["--workers", "0"],
        ["--workers", "-1"],
        ["--workers", "1.5"],
        ["--area", "../x"],
        ["--resume"],
        ["--refresh-sources", "--run-id", "x", "--overwrite"],
        ["--refresh-sources", "--offline"],
    ],
)
def test_invalid_arguments_do_not_start_production(arguments):
    workflow = Mock()
    with pytest.raises(SystemExit) as result:
        run_cli(production_parser("test", workers=True), workflow, arguments)
    assert result.value.code == 2
    workflow.assert_not_called()


def test_cli_directories_override_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "environment"))
    monkeypatch.setenv("SOURCE_DATA_DIR", str(tmp_path / "environment_sources"))
    main = Mock(return_value=tmp_path / "result")
    run_cli(
        production_parser("test"),
        main,
        [
            "--data-dir",
            str(tmp_path / "cli"),
            "--output-root",
            str(tmp_path / "output"),
            "--area",
            "38",
        ],
    )
    arguments = main.call_args.kwargs
    assert arguments["area"] == "waterschap_38"
    assert arguments["data_store"].source_data_dir == tmp_path / "cli" / "source_data"
    assert arguments["data_store"].processed_data_dir == tmp_path / "output"


def test_offline_missing_and_refresh_once(tmp_path):
    path = tmp_path / "source"
    download = Mock(side_effect=lambda: path.write_text("new"))
    with pytest.raises(FileNotFoundError, match="offline"):
        SourcePreparation(offline=True).ensure(path, download)
    download.assert_not_called()
    path.write_text("old")
    SourcePreparation().ensure(path, download)
    download.assert_not_called()
    preparation = SourcePreparation(refresh=True)
    preparation.ensure(path, download)
    preparation.ensure(path, download)
    download.assert_called_once()
    for arguments in ({"resume": True}, {"overwrite": True}, {"offline": True}):
        options = {
            "refresh_sources": True,
            "offline": False,
            "resume": False,
            "overwrite": False,
        }
        options.update(arguments)
        with pytest.raises(ValueError):
            source_options(None, **options)


def test_failed_cache_preparation_is_retried(tmp_path):
    source, output = tmp_path / "source", tmp_path / "output"
    source.write_text("old")
    build = Mock(side_effect=lambda: output.write_text("prepared"))
    prepare_cached(output, {"input": source}, build)
    prepare_cached(output, {"input": source}, build)
    assert build.call_count == 1
    source.write_text("changed source")
    with pytest.raises(RuntimeError):
        prepare_cached(
            output, {"input": source}, Mock(side_effect=RuntimeError("failed"))
        )
    prepare_cached(output, {"input": source}, build)
    assert build.call_count == 2


@pytest.mark.parametrize("size", [5000, 10000])
def test_named_polygon_is_independent_of_tile_size(size):
    rows = []
    for y in range(510000, 530000, size):
        for x in range(100000, 120000, size):
            rows.append(
                {
                    "tile_id": f"{x}_{y}",
                    "xmin": x,
                    "ymin": y,
                    "geometry": box(x, y, x + size, y + size),
                }
            )
    grid = gpd.GeoDataFrame(rows, crs=28992)
    area = ProductionArea("alkmaar", NAMED_AREAS["alkmaar"], "EPSG:28992")
    selected = select_area_tiles(grid, area)
    assert selected.geometry.union_all().covers(area.geometry)
    assert all(geometry.area == size**2 for geometry in selected.geometry)
    assert area_name("38") == "waterschap_38"


def _worker_log(path):
    with tile_logging(path):
        get_logger("waterlagen.test.worker").info("worker-message")


def test_logging_collects_spawned_and_nested_records_and_restores_caller(tmp_path):
    root = logging.getLogger()
    package = logging.getLogger("waterlagen")
    root_state = root.handlers[:], root.level
    package_state = package.handlers[:], package.level, package.propagate
    with production_logging():
        get_logger("waterlagen.test").info("preparation-message")
        with run_log(tmp_path / "parent"):
            get_logger("waterlagen.test").info("parent-message")
            with production_logging(), run_log(tmp_path / "nested"):
                get_logger("waterlagen.test").info("nested-message")
                with ProcessPoolExecutor(
                    max_workers=1, mp_context=get_context("spawn"), **executor_logging()
                ) as pool:
                    pool.submit(_worker_log, tmp_path / "tile.log").result(timeout=30)
    content = (tmp_path / "parent" / "productie.log").read_text()
    for message in (
        "preparation-message",
        "parent-message",
        "nested-message",
        "worker-message",
    ):
        assert content.count(message) == 1
    assert not (tmp_path / "nested" / "productie.log").exists()
    assert not (tmp_path / "tile.log").exists()
    assert (root.handlers, root.level) == root_state
    assert (package.handlers, package.level, package.propagate) == package_state
