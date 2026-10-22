"""Run the published scripts against real API signatures, without downloads."""

import ast
import importlib
import inspect
import runpy
import socket
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import create_autospec

import geopandas as gpd
import pytest
import requests
from shapely.geometry import LineString, Point, box

from waterlagen._downloads import GeoPackageDownload
from waterlagen.areas import NAMED_AREAS
from waterlagen.bgt import BgtCustomDownload, BgtDownload
from waterlagen.brp.download import BrpDownload, BrpRelease
from waterlagen.cbs import StatLineDownload
from waterlagen.datastore import DataStore

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "reference" / "voorbeelden"


@dataclass(frozen=True)
class Call:
    module: str
    function: str
    result_kind: str = "path"


DOWNLOADS = {
    "ahn": [Call("waterlagen.ahn", "download_ahn")],
    "bag": [Call("waterlagen.bag", "download_bag_light")],
    "bestuurlijke_gebieden": [
        Call(
            "waterlagen.administratieve_gebieden",
            "download_bestuurlijke_gebieden",
            "gpkg",
        )
    ],
    "bgt": [Call("waterlagen.bgt", "bgt_custom_download", "bgt")],
    "brp": [Call("waterlagen.brp", "download_brp", "brp")],
    "cbs": [
        Call(
            "waterlagen.administratieve_gebieden",
            "download_wijk_buurtkaart_2025",
            "gpkg",
        ),
        Call("waterlagen.cbs", "download_buurtgegevens_2025", "statline"),
    ],
    "dijkringen": [Call("waterlagen.dijkringen", "download_dijkringen", "gpkg")],
    "hydamo": [Call("waterlagen.hydamo", "download_hydamo", "gpkg")],
    "rijkswateren": [Call("waterlagen.rijkswateren", "download_rijkswateren", "path")],
    "liwo": [Call("waterlagen.liwo", "download_raster")],
    "osm_canals": [Call("waterlagen.osm_waterlopen", "download_osm_canals", "path")],
    "osm_drinkwater": [
        Call(
            "waterlagen.functioneel_landgebruik.osm_drinkwater",
            "download_osm_drinkwater",
        )
    ],
    "top10nl": [Call("waterlagen.top10nl", "download_top10nl")],
    "waterketen_damo": [
        Call("waterlagen.waterketen_damo", "download_waterketen_damo", "gpkg")
    ],
    "waterschapsgrenzen": [
        Call(
            "waterlagen.administratieve_gebieden", "download_waterschapsgrenzen", "gpkg"
        )
    ],
}
PRODUCTS = {
    "afwateringseenheden": "waterlagen.afwateringseenheden.productie",
    "autos": "waterlagen.autos.productie",
    "dem": "waterlagen.dem.workflow",
    "functioneel_landgebruik": "waterlagen.functioneel_landgebruik.productie",
    "inwoners": "waterlagen.inwoners.productie",
}


@pytest.fixture(autouse=True)
def isolated_example(tmp_path, monkeypatch):
    """Fail immediately on accidental network access and isolate all storage."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "environment_data"))
    monkeypatch.setenv("SOURCE_DATA_DIR", str(tmp_path / "environment_sources"))
    monkeypatch.setenv("PROCESSED_DATA_DIR", str(tmp_path / "environment_processed"))

    def no_network(*args, **kwargs):
        raise AssertionError("Example checks must not access the network")

    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)


def _result(kind, path):
    """Return real result types so renamed metadata fields break the examples."""
    if kind == "gpkg":
        return GeoPackageDownload("fixture", path, 0, True)
    if kind == "brp":
        return BrpDownload(path, BrpRelease("fixture", path.name, None, None))
    if kind == "bgt":
        return BgtCustomDownload(path, ("waterdeel", "pand"), None, None)
    if kind == "statline":
        return StatLineDownload(path, "fixture", "fixture", 2025, 1, True)
    assert kind == "path"
    return path


def _assert_store(store, root):
    assert isinstance(store, DataStore)
    assert store.data_dir.resolve() == root
    assert store.source_data_dir.resolve() == root / "source_data"
    assert store.processed_data_dir.resolve() == root / "processed_data"


@pytest.mark.parametrize("name", DOWNLOADS)
def test_download_example_runs_with_current_api(name, tmp_path, monkeypatch, capsys):
    calls = []
    output = tmp_path / "local_result"
    output.write_text("stand-in for an already downloaded result")
    for call in DOWNLOADS[name]:
        module = importlib.import_module(call.module)
        function = getattr(module, call.function)
        signature = inspect.signature(function)
        mocked = create_autospec(
            function, return_value=_result(call.result_kind, output)
        )
        monkeypatch.setattr(module, call.function, mocked)
        calls.append((signature, mocked))

    path = EXAMPLES / f"download_{name}.py"
    runpy.run_path(str(path))
    for _, mocked in calls:
        mocked.assert_not_called()

    # Execute exactly the file offered for download, including its __main__ guard.
    runpy.run_path(str(path), run_name="__main__")
    assert str(output) in capsys.readouterr().out
    for signature, mocked in calls:
        mocked.assert_called_once()
        arguments = signature.bind(
            *mocked.call_args.args, **mocked.call_args.kwargs
        ).arguments
        assert (
            arguments.get("overwrite") is False or arguments.get("missing_only") is True
        )
        if "poly_mask" in arguments:
            assert arguments["poly_mask"].equals(NAMED_AREAS["alkmaar_centrum"])
        if "data_store" in arguments:
            _assert_store(arguments["data_store"], tmp_path / "data")
        for key in ("download_dir", "ahn_dir", "target_path"):
            if key in arguments:
                assert (
                    arguments[key]
                    .resolve()
                    .is_relative_to(tmp_path / "data" / "source_data")
                )


def _mock_api(monkeypatch, module_name, function_name, result):
    module = importlib.import_module(module_name)
    mocked = create_autospec(getattr(module, function_name), return_value=result)
    monkeypatch.setattr(module, function_name, mocked)
    return mocked


def _mock_downloads(monkeypatch, tmp_path):
    mocks = {}
    for name, calls in DOWNLOADS.items():
        for call in calls:
            path = tmp_path / (name + "_" + call.function)
            mocks[call.function] = _mock_api(
                monkeypatch, call.module, call.function, _result(call.result_kind, path)
            )
    path = tmp_path / "bgt.gpkg"
    mocks["download_bgt"] = _mock_api(
        monkeypatch,
        "waterlagen.bgt",
        "download_bgt",
        BgtDownload(
            "fixture", path.with_suffix(".zip"), path, 0, 6, "EPSG:28992", False
        ),
    )
    return mocks


def _run_product(name, tmp_path, replacements=()):
    path = EXAMPLES / f"produceer_{name}.py"
    if replacements:
        source = path.read_text(encoding="utf-8")
        for original, replacement in replacements:
            assert original in source
            source = source.replace(original, replacement)
        path = tmp_path / path.name
        path.write_text(source, encoding="utf-8")
    return runpy.run_path(str(path), run_name="__main__")


@pytest.mark.parametrize("name", ["autos", "inwoners"])
def test_vbo_examples_keep_complete_buurten_and_calculate(name, tmp_path, monkeypatch):
    from waterlagen.vbo_buurt import VboBuurtBuild, sorteer_op_hilbert

    downloads = _mock_downloads(monkeypatch, tmp_path)
    # The first buurt crosses the area boundary; the second only touches it.
    buurten = gpd.GeoDataFrame(
        {
            "buurtcode": ["BU1", "BU2"],
            "aantal_woonvbo": [2, 1],
            "aantal_inwoners": [100, 10],
            "aantal_huishoudens": [50, 5],
            "personenautos_totaal": [70, 5],
        },
        geometry=[
            box(111000, 515500, 113500, 516750),
            box(111250, 516750, 112250, 517000),
        ],
        crs="EPSG:28992",
    )
    vbos = sorteer_op_hilbert(
        gpd.GeoDataFrame(
            {
                "identificatie": ["inside", "outside", "other"],
                "buurtcode": ["BU1", "BU1", "BU2"],
            },
            geometry=[
                Point(111500, 516000),
                Point(113000, 516000),
                Point(111500, 516800),
            ],
            crs=buurten.crs,
        )
    )
    bag_path, buurt_path = tmp_path / "vbos.gpkg", tmp_path / "buurten.gpkg"
    vbos.to_file(bag_path, layer="bag_vbo", driver="GPKG")
    buurten.to_file(buurt_path, layer="cbs_buurt", driver="GPKG")
    preparation = _mock_api(
        monkeypatch,
        "waterlagen.vbo_buurt",
        "bouw_vbo_buurt",
        VboBuurtBuild(bag_path, buurt_path, 3, 3, 2, False),
    )

    result = _run_product(name, tmp_path)
    preparation.assert_called_once()
    assert preparation.call_args.kwargs["overwrite"] is False
    assert set(result["resultaat"].identificatie) == {"inside", "outside"}
    assert not NAMED_AREAS["alkmaar_centrum"].contains(
        result["resultaat"].set_index("identificatie").loc["outside"].geometry
    )
    saved = gpd.read_file(result["target"], layer=name)
    if name == "autos":
        assert saved.personenautos.sum() == pytest.approx(70)
    else:
        assert saved.inwoners_obv_woonvbo.sum() == pytest.approx(100)
        assert saved.inwoners_obv_huishoudens.tolist() == [2.0, 2.0]
    for function in (
        "download_bag_light",
        "download_wijk_buurtkaart_2025",
        "download_buurtgegevens_2025",
    ):
        downloads[function].assert_called_once()
    # An existing experiment is protected before downloads/preparation run again.
    with pytest.raises(FileExistsError):
        _run_product(name, tmp_path)
    preparation.assert_called_once()


def test_landuse_example_passes_editable_settings_and_all_sources(
    tmp_path, monkeypatch
):
    downloads = _mock_downloads(monkeypatch, tmp_path)
    index = _mock_api(
        monkeypatch,
        "waterlagen.functioneel_landgebruik.gebouwen",
        "ensure_building_index",
        tmp_path / "index.sqlite",
    )
    polygonize = _mock_api(
        monkeypatch,
        "waterlagen.liwo",
        "polygonize_selected",
        tmp_path / "buitendijks.gpkg",
    )
    build = _mock_api(
        monkeypatch,
        "waterlagen.functioneel_landgebruik",
        "bouw_functioneel_landgebruik",
        tmp_path / "landuse.tif",
    )
    result = _run_product(
        "functioneel_landgebruik",
        tmp_path,
        [
            ("RESOLUTION_M = 0.5", "RESOLUTION_M = 1.0"),
            ("GAP_FILL_DISTANCE_M = 1.0", "GAP_FILL_DISTANCE_M = 2.0"),
            ("MAPPING_CSV = None", 'MAPPING_CSV = Path("eigen.csv")'),
        ],
    )
    build.assert_called_once()
    arguments = build.call_args.kwargs
    assert arguments["bounds"] == NAMED_AREAS["alkmaar_centrum"].bounds
    assert arguments["resolution_m"] == 1.0
    assert arguments["gap_fill_distance_m"] == 2.0
    assert arguments["mapping_csv"] == Path("eigen.csv")
    assert arguments["download_missing_sources"] is False
    assert arguments["building_index_path"] == index.return_value
    assert (
        arguments["sources"].bgt_gpkg
        == downloads["download_bgt"].return_value.target_path
    )
    assert arguments["sources"].bag_gpkg == downloads["download_bag_light"].return_value
    assert (
        arguments["sources"].gemalen_gpkg
        == downloads["download_hydamo"].return_value.target_path
    )
    assert (
        arguments["sources"].rwzi_gpkg
        == downloads["download_waterketen_damo"].return_value.target_path
    )
    assert (
        arguments["sources"].drinking_water_gpkg
        == downloads["download_osm_drinkwater"].return_value
    )
    polygonize.assert_called_once()
    assert result["resultaat"] == build.return_value


def test_dem_example_requests_full_building_context_and_passes_config(
    tmp_path, monkeypatch
):
    downloads = _mock_downloads(monkeypatch, tmp_path)
    build = _mock_api(
        monkeypatch, "waterlagen.dem", "bouw_dem_tiles", tmp_path / "dem.tif"
    )
    landuse_dir = (
        tmp_path
        / "data/processed_data/voorbeelden/alkmaar_centrum"
        / "experiment_01/functioneel_landgebruik"
    )
    landuse_dir.mkdir(parents=True)
    buildings = gpd.GeoDataFrame(
        geometry=[box(112200, 516000, 113000, 516050)], crs="EPSG:28992"
    )
    buildings.to_file(landuse_dir / "gebouwen.gpkg", layer="gebouwen", driver="GPKG")
    _run_product(
        "dem",
        tmp_path,
        [
            (
                "interpolation_max_distance_m=250.0",
                "interpolation_max_distance_m=125.0",
            ),
            ("building_percentile=75.0", "building_percentile=60.0"),
            ("building_offset_m=0.05", "building_offset_m=0.15"),
        ],
    )
    build.assert_called_once()
    config = build.call_args.kwargs["config"]
    assert config.interpolation_max_distance_m == 125.0
    assert config.building_percentile == 60.0
    assert config.building_offset_m == 0.15
    assert build.call_args.kwargs["landuse_tiles"] == [
        landuse_dir.relative_to(tmp_path) / "functioneel_landgebruik.tif"
    ]
    mask = downloads["download_ahn"].call_args.kwargs["poly_mask"]
    assert mask.covers(buildings.geometry.iloc[0].buffer(125))
    assert mask.covers(NAMED_AREAS["alkmaar_centrum"].buffer(125))


@pytest.mark.parametrize("with_brandlagen", [False, True])
def test_afwatering_example_connects_steps_and_passes_settings(
    tmp_path, monkeypatch, with_brandlagen
):
    from waterlagen.afwateringseenheden import (
        AfwateringseenhedenTilesResult,
        WatersysteemResult,
        WatersysteemSources,
    )

    downloads = _mock_downloads(monkeypatch, tmp_path)
    hydro = gpd.GeoDataFrame(
        {"bron_id": ["p", "s"], "categorieoppwaterlichaam": ["primair", "secundair"]},
        geometry=[
            LineString([(111500, 516000), (111600, 516000)]),
            LineString([(111550, 516000), (111550, 516050)]),
        ],
        crs="EPSG:28992",
    )
    points = gpd.GeoDataFrame(geometry=[Point(111550, 516000)], crs=hydro.crs)
    module = "waterlagen.afwateringseenheden"
    read_sources = _mock_api(
        monkeypatch,
        module,
        "read_watersysteem_sources",
        WatersysteemSources(
            hydro.iloc[:1],
            hydro.iloc[1:],
            hydro.iloc[:1],
            points,
            culverts=hydro.iloc[:1].copy(),
        ),
    )
    prepare = _mock_api(
        monkeypatch, module, "prepare_watersysteem", WatersysteemResult(hydro, points)
    )
    write = _mock_api(
        monkeypatch, module, "write_watersysteem", tmp_path / "network.gpkg"
    )
    calculate = _mock_api(
        monkeypatch,
        module,
        "calculate_afwateringseenheden_tiles",
        AfwateringseenhedenTilesResult(
            tmp_path, (), tmp_path / "result.gpkg", points, (), ()
        ),
    )
    replacements = [
        ("TOLERANCE_M = 2.0", "TOLERANCE_M = 3.0"),
        ("TILE_SIZE_M = 1000", "TILE_SIZE_M = 2000"),
        ("TILE_BUFFER_M = 2000", "TILE_BUFFER_M = 1500"),
        ("BURN_DEPTH_M = 100.0", "BURN_DEPTH_M = 80.0"),
        ("DUIKER_TOLERANCE_M = 0.5", "DUIKER_TOLERANCE_M = 0.3"),
        (
            "MAX_AANSLUITLENGTE_M: float | None = None",
            "MAX_AANSLUITLENGTE_M: float | None = 25.0",
        ),
    ]
    if with_brandlagen:
        hydro.to_file(tmp_path / "brandlagen.gpkg", layer="waterlopen", driver="GPKG")
        (tmp_path / "brandlagen.toml").write_text(
            "[defaults]\nbrandwaarde = -3.0\nprioriteit = 2\n"
            '[[lagen]]\npath = "brandlagen.gpkg"\nlayer = "waterlopen"\n',
            encoding="utf-8",
        )
        replacements.append(
            (
                "BRANDLAGEN_CONFIG: Path | None = None",
                'BRANDLAGEN_CONFIG: Path | None = Path("brandlagen.toml")',
            )
        )
    _run_product("afwateringseenheden", tmp_path, replacements)
    prepare.assert_called_once()
    assert prepare.call_args.args[0].bron_id.tolist() == ["p"]
    assert write.call_args.kwargs["hydroobject_secundair"].bron_id.tolist() == ["s"]
    assert prepare.call_args.kwargs["tolerance"] == 3.0
    assert prepare.call_args.kwargs["duiker_tolerance"] == 0.3
    assert prepare.call_args.kwargs["max_aansluitlengte"] == 25.0
    assert (
        prepare.call_args.kwargs["duikersifonhevel"]
        is read_sources.return_value.culverts
    )
    assert (
        prepare.call_args.kwargs["hydroobject_primair"]
        is read_sources.return_value.primary
    )
    assert write.call_args.kwargs["controle_path"].name == "controle.gpkg"
    assert write.call_args.kwargs["watersysteem"] is prepare.return_value
    assert write.call_args.kwargs["secondary_connection_tolerance"] == 3.0
    calculate.assert_called_once()
    arguments = calculate.call_args.kwargs
    assert arguments["watersysteem_path"] == write.return_value
    assert arguments["burn_depth_m"] == 80.0
    assert arguments["tile_size_m"] == 2000
    assert arguments["tile_buffer_m"] == 1500
    if with_brandlagen:
        assert arguments["brandlagen"].brandwaarde == -3.0
        assert arguments["brandlagen"].lagen[0].path == tmp_path / "brandlagen.gpkg"
    else:
        assert arguments["brandlagen"] is None
    mask = downloads["download_ahn"].call_args.kwargs["poly_mask"]
    assert mask.equals(read_sources.call_args.kwargs["spatial_selection"])
    x, y = NAMED_AREAS["alkmaar_centrum"].bounds[:2]
    assert mask.covers(box(x, y, x + 2000, y + 2000).buffer(1500))


@pytest.mark.parametrize("name", PRODUCTS)
def test_product_imports_are_inert_and_use_building_blocks(name, tmp_path, monkeypatch):
    downloads = _mock_downloads(monkeypatch, tmp_path)
    path = EXAMPLES / f"produceer_{name}.py"
    runpy.run_path(str(path))
    for mocked in downloads.values():
        mocked.assert_not_called()
    assert not (tmp_path / "data").exists()
    # Keep the examples below the production entry points.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in set(PRODUCTS.values())
            assert not any(alias.name == "main" for alias in node.names)


def test_every_published_example_has_a_contract_check_and_download_link():
    expected = {f"download_{name}.py" for name in DOWNLOADS}
    expected |= {f"produceer_{name}.py" for name in PRODUCTS}
    assert {path.name for path in EXAMPLES.glob("*.py")} == expected
    pages = "\n".join(
        (ROOT / "docs" / "reference" / name).read_text(encoding="utf-8")
        for name in ("bronlagen-downloaden.md", "bewerkte-lagen-produceren.md")
    )
    for name in expected:
        assert f'--8<-- "docs/reference/voorbeelden/{name}"' in pages
        assert f"(voorbeelden/{name})" in pages
