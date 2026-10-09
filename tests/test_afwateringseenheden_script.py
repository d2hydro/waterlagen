import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, box


def _load_afwateringseenheden_script():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "afwateringseenheden.py"
    )
    spec = importlib.util.spec_from_file_location(
        "afwateringseenheden_script", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def production(tmp_path, monkeypatch):
    script = _load_afwateringseenheden_script()
    data_store = SimpleNamespace(
        ahn_dir=tmp_path / "source" / "ahn",
        source_data_dir=tmp_path / "source",
        processed_data_dir=tmp_path / "processed",
        afwateringseenheden_path=tmp_path / "processed" / "afwateringseenheden",
    )
    generic_ahn = data_store.ahn_dir / "dtm_05" / "dtm_05.vrt"
    generic_watersysteem = data_store.afwateringseenheden_path / "watersysteem.gpkg"
    for path in (generic_ahn, generic_watersysteem):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"existing data for another area")

    boundaries = gpd.GeoDataFrame(
        {"waterbeheercode": ["38", "99"]},
        geometry=[
            box(150000, 400000, 151000, 401000),
            box(160000, 410000, 161000, 411000),
        ],
        crs="EPSG:28992",
    )
    hydroobjecten = gpd.GeoDataFrame(
        {script.CATEGORIE_OPPERVLAKTEWATER_COLUMN: ["primair", "secundair"]},
        geometry=[
            LineString([(150000, 400000), (150100, 400000)]),
            LineString([(150100, 400000), (150100, 400100)]),
        ],
        crs=boundaries.crs,
    )
    puntobjecten = gpd.GeoDataFrame(
        geometry=[Point(150100, 400000)], crs=boundaries.crs
    )
    selected_ahn = tmp_path / "selected_ahn.vrt"
    hydamo = SimpleNamespace(target_path=tmp_path / "hydamo.gpkg")
    watersysteem = object()

    monkeypatch.setattr(script, "datastore", data_store)
    monkeypatch.setattr(script.settings, "afwateringseenheden_workers", 3)
    monkeypatch.setattr(script, "require_pcraster", Mock())
    monkeypatch.setattr(script, "init_logger", Mock(return_value=Mock()))
    monkeypatch.setattr(
        script, "download_waterschapsgrenzen", Mock(return_value=hydamo)
    )
    monkeypatch.setattr(
        script, "read_waterschapsgrenzen_layer", Mock(return_value=boundaries)
    )
    monkeypatch.setattr(
        script, "normaliseer_waterschapsgrenzen", Mock(return_value=boundaries)
    )
    monkeypatch.setattr(script, "download_ahn", Mock(return_value=selected_ahn))
    monkeypatch.setattr(
        script,
        "download_bestuurlijke_gebieden",
        Mock(return_value=SimpleNamespace(target_path=tmp_path / "bestuurlijke.gpkg")),
    )
    monkeypatch.setattr(script, "download_hydamo", Mock(return_value=hydamo))
    monkeypatch.setattr(script, "read_hydroobjecten", Mock(return_value=hydroobjecten))
    monkeypatch.setattr(script, "read_puntobjecten", Mock(return_value=puntobjecten))
    monkeypatch.setattr(script, "prepare_watersysteem", Mock(return_value=watersysteem))
    monkeypatch.setattr(
        script,
        "write_watersysteem",
        Mock(side_effect=lambda **kwargs: kwargs["output_path"]),
    )
    monkeypatch.setattr(
        script,
        "calculate_afwateringseenheden_tiles",
        Mock(
            return_value=SimpleNamespace(
                tile_results=(),
                skipped_tile_ids=(),
                boundary_issue_tile_ids=(),
                merged_path=None,
            )
        ),
    )
    for name in (
        "GDAL_NUM_THREADS",
        "VRT_NUM_THREADS",
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
    ):
        monkeypatch.setenv(name, "2")

    return SimpleNamespace(
        script=script,
        boundaries=boundaries,
        hydroobjecten=hydroobjecten,
        puntobjecten=puntobjecten,
        selected_ahn=selected_ahn,
        hydamo=hydamo,
        watersysteem=watersysteem,
        generic_watersysteem=generic_watersysteem,
    )


@pytest.mark.parametrize(
    ("arguments", "expected_codes", "expected_workers"),
    [
        (None, ["38"], 3),
        ([], ["38"], 3),
        (["--waterbeheercode", "99"], ["99"], 3),
        (["--waterbeheercode", "99", "38"], ["99", "38"], 3),
        (["--waterbeheercode", "38", "99", "38"], ["38", "99"], 3),
        (["--waterbeheercode", "38", "99", "--workers", "2"], ["38", "99"], 2),
        (["--workers", "1"], ["38"], 1),
    ],
)
def test_script_prepares_each_area_despite_existing_generic_files(
    production, tmp_path, arguments, expected_codes, expected_workers
):
    script = production.script
    if arguments is None:
        script.main()
    else:
        script.main(**vars(script._parse_args(arguments)))

    script.download_waterschapsgrenzen.assert_called_once_with(overwrite=False)
    assert script.calculate_afwateringseenheden_tiles.call_count == len(expected_codes)
    output_dirs = []
    for index, code in enumerate(expected_codes):
        spatial_mask = (
            production.boundaries.loc[
                production.boundaries["waterbeheercode"] == code, "geometry"
            ]
            .union_all()
            .buffer(script.BUFFER_M)
        )
        assert script.download_ahn.call_args_list[index].kwargs == {
            "poly_mask": spatial_mask,
            "missing_only": True,
        }
        assert script.download_bestuurlijke_gebieden.call_args_list[index].kwargs == {
            "year": script.DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
            "overwrite": False,
        }
        assert script.download_hydamo.call_args_list[index].kwargs == {
            "overwrite": False
        }
        hydro_call = script.read_hydroobjecten.call_args_list[index]
        assert hydro_call.args == (production.hydamo.target_path,)
        assert hydro_call.kwargs == {"spatial_selection": spatial_mask}
        punt_call = script.read_puntobjecten.call_args_list[index]
        assert punt_call.args == (production.hydamo.target_path,)
        assert punt_call.kwargs == {
            "layers": ["gemaal", "stuw"],
            "spatial_selection": spatial_mask,
            "waterbeheercodes": [code],
        }
        prepare_call = script.prepare_watersysteem.call_args_list[index]
        assert prepare_call.args[0].equals(production.hydroobjecten.iloc[[0]])
        assert prepare_call.args[1] is production.puntobjecten
        assert prepare_call.kwargs["hydroobject_secundair"].equals(
            production.hydroobjecten.iloc[[1]]
        )
        write_args = script.write_watersysteem.call_args_list[index].kwargs
        run_dir = write_args["output_path"].parent
        assert (
            run_dir.parent
            == script.datastore.afwateringseenheden_path / f"waterschap_{code}"
        )
        assert run_dir.name.endswith("Z")
        assert len(run_dir.name) == 16
        assert write_args["output_path"] == run_dir / "watersysteem.gpkg"
        assert write_args["watersysteem"] is production.watersysteem
        assert write_args["overwrite"] is False
        tile_args = script.calculate_afwateringseenheden_tiles.call_args_list[
            index
        ].kwargs
        assert tile_args["workers"] == expected_workers
        assert tile_args["tile_size_m"] == 10000
        assert tile_args["tile_buffer_m"] == 2000
        assert tile_args["burn_depth_m"] == 100
        assert tile_args["max_fill_depth_m"] == 50
        assert tile_args["random_seed"] == 12345
        assert tile_args["watersysteem_path"] == write_args["output_path"]
        assert tile_args["ahn_vrt_path"] == production.selected_ahn
        assert tile_args["landsgrens_path"] == tmp_path / "bestuurlijke.gpkg"
        assert tile_args["merged_output_path"] == run_dir / "afwateringseenheden.gpkg"
        output_dirs.append(run_dir)
    assert len(set(output_dirs)) == len(expected_codes)
    assert (
        production.generic_watersysteem.read_bytes()
        == b"existing data for another area"
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--tile-size-m", "5000"],
        ["--workers", "0"],
        ["--workers", "-1"],
        ["--workers", "1.5"],
        ["--buffer-m", "1000"],
        ["--tile-buffer-m", "1000"],
        ["--burn-depth-m", "50"],
        ["--max-fill-depth-m", "25"],
        ["--random-seed", "321"],
        ["--waterbeheercode"],
        ["--waterbeheercode", "  "],
        ["--waterbeheercode", "38,99"],
        ["--waterbeheercode", "../38"],
    ],
)
def test_invalid_cli_arguments_stop_before_production(arguments, monkeypatch, capsys):
    script = _load_afwateringseenheden_script()
    download = Mock()
    monkeypatch.setattr(script, "download_waterschapsgrenzen", download)
    with pytest.raises(SystemExit) as error:
        script.main(**vars(script._parse_args(arguments)))
    assert error.value.code == 2
    assert arguments[0] in capsys.readouterr().err
    download.assert_not_called()


def test_cli_help_shows_options_without_production(monkeypatch, capsys):
    script = _load_afwateringseenheden_script()
    pcraster = Mock()
    monkeypatch.setattr(script, "require_pcraster", pcraster)
    with pytest.raises(SystemExit) as result:
        script.main(**vars(script._parse_args(["--help"])))
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert "--waterbeheercode" in help_text
    assert "--tile-size-m" not in help_text
    assert "--workers" in help_text
    pcraster.assert_not_called()


def test_unknown_code_stops_entire_batch_before_large_downloads(production):
    script = production.script
    with pytest.raises(
        ValueError, match="Geen waterschapsgrens gevonden voor code.s.: 123"
    ):
        script.main(waterbeheercodes=["38", "123"])
    script.download_ahn.assert_not_called()
    script.download_hydamo.assert_not_called()
    script.calculate_afwateringseenheden_tiles.assert_not_called()
    assert not list(script.datastore.afwateringseenheden_path.glob("waterschap_*"))


def test_failure_stops_batch_before_next_waterschap(production):
    script = production.script
    script.calculate_afwateringseenheden_tiles.side_effect = RuntimeError(
        "Productie mislukt"
    )
    with pytest.raises(RuntimeError, match="Productie mislukt"):
        script.main(waterbeheercodes=["38", "99"])
    script.calculate_afwateringseenheden_tiles.assert_called_once()
    script.read_puntobjecten.assert_called_once()
    assert script.read_puntobjecten.call_args.kwargs["waterbeheercodes"] == ["38"]


def test_explicit_run_resume_and_overwrite(production):
    script = production.script
    script.main(run_id="test")
    original_path = script.calculate_afwateringseenheden_tiles.call_args.kwargs[
        "output_dir"
    ]
    for mode in ("resume", "overwrite"):
        script.main(run_id="test", **{mode: True})
        args = script.calculate_afwateringseenheden_tiles.call_args.kwargs
        assert args["output_dir"] == original_path
        assert args["overwrite"] is (mode == "overwrite")
        assert script.write_watersysteem.call_args.kwargs["overwrite"] is (
            mode == "overwrite"
        )
