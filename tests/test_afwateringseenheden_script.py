import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import geopandas as gpd
from shapely.geometry import LineString, Point, box


def _load_afwateringseenheden_script():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "afwateringseenheden_aa_en_maas.py"
    )
    spec = importlib.util.spec_from_file_location(
        "afwateringseenheden_script", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_script_prepares_area_inputs_despite_existing_generic_files(
    tmp_path, monkeypatch
):
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

    boundary = box(150000, 400000, 151000, 401000)
    boundaries = gpd.GeoDataFrame(
        {"waterbeheercode": [script.WATERBEHEERCODE]},
        geometry=[boundary],
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

    script.main()

    spatial_mask = boundary.buffer(script.BUFFER_M)
    script.download_ahn.assert_called_once_with(
        poly_mask=spatial_mask, missing_only=True
    )
    script.download_bestuurlijke_gebieden.assert_called_once_with(
        year=script.DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR, overwrite=False
    )
    script.download_hydamo.assert_called_once_with(overwrite=False)
    script.read_hydroobjecten.assert_called_once_with(
        hydamo.target_path, spatial_selection=spatial_mask
    )
    script.read_puntobjecten.assert_called_once_with(
        hydamo.target_path,
        layers=["gemaal", "stuw"],
        spatial_selection=spatial_mask,
        waterbeheercodes=[script.WATERBEHEERCODE],
    )
    assert script.prepare_watersysteem.call_args.args[0].equals(hydroobjecten.iloc[[0]])
    assert script.prepare_watersysteem.call_args.args[1] is puntobjecten
    assert script.prepare_watersysteem.call_args.kwargs["hydroobject_secundair"].equals(
        hydroobjecten.iloc[[1]]
    )
    write_args = script.write_watersysteem.call_args.kwargs
    run_dir = write_args["output_path"].parent
    assert run_dir.parent == data_store.afwateringseenheden_path
    assert run_dir.name.startswith("aa_en_maas_")
    assert write_args["output_path"] == run_dir / "watersysteem.gpkg"
    assert write_args["watersysteem"] is watersysteem
    assert write_args["overwrite"] is False
    tile_args = script.calculate_afwateringseenheden_tiles.call_args.kwargs
    assert tile_args["workers"] == 3
    assert tile_args["watersysteem_path"] == write_args["output_path"]
    assert tile_args["ahn_vrt_path"] == selected_ahn
    assert tile_args["landsgrens_path"] == tmp_path / "bestuurlijke.gpkg"
    assert generic_watersysteem.read_bytes() == b"existing data for another area"
