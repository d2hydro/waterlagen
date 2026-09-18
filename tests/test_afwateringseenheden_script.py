from types import SimpleNamespace
from unittest.mock import Mock

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, box

from waterlagen.afwateringseenheden import production
from waterlagen.datastore import DataStore


@pytest.mark.parametrize("waterbeheercode, workers", [("38", None), ("25", 2)])
def test_production_prepares_area_inputs_despite_existing_generic_files(
    tmp_path, monkeypatch, waterbeheercode, workers
):
    script = production
    config = production.ProductionConfig(
        waterbeheercode=waterbeheercode, workers=workers
    )
    data_store = DataStore(
        data_dir=tmp_path,
        source_data_dir=tmp_path / "source",
        processed_data_dir=tmp_path / "processed",
        _env_file=None,
    )
    generic_ahn = data_store.ahn_dir / "dtm_05" / "dtm_05.vrt"
    generic_watersysteem = data_store.afwateringseenheden_path / "watersysteem.gpkg"
    for path in (generic_ahn, generic_watersysteem):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"existing data for another area")

    boundary = box(150000, 400000, 151000, 401000)
    boundaries = gpd.GeoDataFrame(
        {"waterbeheercode": [config.waterbeheercode]},
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
                merged_path=tmp_path / "result.gpkg",
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

    result = script.produce_afwateringseenheden(config, data_store=data_store)
    assert result == tmp_path / "result.gpkg"

    spatial_mask = boundary.buffer(config.buffer_m)
    script.download_ahn.assert_called_once_with(
        ahn_dir=data_store.ahn_dir, poly_mask=spatial_mask, missing_only=True
    )
    script.download_bestuurlijke_gebieden.assert_called_once_with(
        year=script.DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
        download_dir=data_store.administratieve_gebieden_dir,
        overwrite=False,
    )
    script.download_hydamo.assert_called_once_with(
        download_dir=data_store.hydamo_dir, overwrite=False
    )
    script.read_hydroobjecten.assert_called_once_with(
        hydamo.target_path, spatial_selection=spatial_mask
    )
    script.read_puntobjecten.assert_called_once_with(
        hydamo.target_path,
        layers=["gemaal", "stuw"],
        spatial_selection=spatial_mask,
        waterbeheercodes=[config.waterbeheercode],
    )
    assert script.prepare_watersysteem.call_args.args[0].equals(hydroobjecten.iloc[[0]])
    assert script.prepare_watersysteem.call_args.args[1] is puntobjecten
    assert script.prepare_watersysteem.call_args.kwargs["hydroobject_secundair"].equals(
        hydroobjecten.iloc[[1]]
    )
    write_args = script.write_watersysteem.call_args.kwargs
    run_dir = write_args["output_path"].parent
    assert run_dir.parent == data_store.afwateringseenheden_path
    prefix = "aa_en_maas_" if waterbeheercode == "38" else "waterschap_25_"
    assert run_dir.name.startswith(prefix)
    assert write_args["output_path"] == run_dir / "watersysteem.gpkg"
    assert write_args["watersysteem"] is watersysteem
    assert write_args["overwrite"] is False
    tile_args = script.calculate_afwateringseenheden_tiles.call_args.kwargs
    assert tile_args["workers"] == (workers or 3)
    assert tile_args["data_store"] is data_store
    assert tile_args["watersysteem_path"] == write_args["output_path"]
    assert tile_args["ahn_vrt_path"] == selected_ahn
    assert tile_args["landsgrens_path"] == tmp_path / "bestuurlijke.gpkg"
    assert generic_watersysteem.read_bytes() == b"existing data for another area"


def test_missing_pcraster_stops_before_downloads(tmp_path, monkeypatch):
    download = Mock()
    monkeypatch.setattr(production, "download_waterschapsgrenzen", download)
    monkeypatch.setattr(
        production,
        "require_pcraster",
        Mock(side_effect=RuntimeError("PCRaster ontbreekt")),
    )
    store = DataStore(data_dir=tmp_path, _env_file=None)
    with pytest.raises(RuntimeError, match="PCRaster"):
        production.produce_afwateringseenheden(data_store=store)
    download.assert_not_called()
    assert not (tmp_path / "processed_data" / "afwateringseenheden").exists()


@pytest.mark.parametrize(
    "values",
    [
        {"waterbeheercode": "../38"},
        {"workers": 0},
        {"buffer_m": -1},
        {"tile_size_m": 0},
        {"tile_buffer_m": float("inf")},
        {"burn_depth_m": float("nan")},
        {"max_fill_depth_m": -1},
        {"random_seed": 0},
    ],
)
def test_production_rejects_invalid_configuration(values):
    with pytest.raises(ValueError):
        production.ProductionConfig(**values)
