import json
from types import SimpleNamespace
from unittest.mock import Mock

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, box

from waterlagen.afwateringseenheden import Brandlaag, BrandlagenConfig
from waterlagen.afwateringseenheden import productie as production
from waterlagen.areas import ProductionArea, area_from_bounds
from waterlagen.datastore import DataStore


@pytest.mark.parametrize("name", ["nederland", "alkmaar", "waterschap_38", "bounds"])
@pytest.mark.parametrize("optional_burn", [False, True])
def test_one_area_product_with_full_tiles_and_selected_authorities(
    tmp_path, monkeypatch, name, optional_burn
):
    store = DataStore(data_dir=tmp_path, _env_file=None)
    area = ProductionArea(name, box(150100, 400100, 151000, 401000), "EPSG:28992")
    if name == "bounds":
        area = area_from_bounds(area.geometry.bounds)
        name = area.value
    hydamo = store.hydamo_dir / "hydamo.gpkg"
    boundary = tmp_path / "boundary.gpkg"
    ahn = tmp_path / "ahn.vrt"
    for path in (boundary, ahn):
        path.write_text("existing")
    ahn.write_text("<VRTDataset />")
    hydro = gpd.GeoDataFrame(
        {
            "categorieoppwaterlichaam": ["primair", "secundair"],
            "nen3610id": ["NL.WBHCODE.38.p", "NL.WBHCODE.30.s"],
        },
        geometry=[LineString([(150000, 400000), (151000, 401000)])] * 2,
        crs=28992,
    )
    hydro.to_file(hydamo, layer="hydroobject")
    points = gpd.GeoDataFrame(
        {"nen3610id": ["NL.WBHCODE.38.point"]},
        geometry=[Point(150000, 400000)],
        crs=28992,
    )
    for layer in ("gemaal", "stuw"):
        points.to_file(hydamo, layer=layer)
    gpd.GeoDataFrame({"nen3610id": []}, geometry=[], crs=28992).to_file(
        hydamo, layer="duikersifonhevel"
    )
    rws = hydro.iloc[:1].copy()
    rws["nen3610id"] = "NL.WBHCODE.80.rws"
    rws.to_file(store.hydamo_dir / "rws_hydamo.gpkg", layer="hydroobject")
    monkeypatch.setattr(production, "require_pcraster", Mock())
    monkeypatch.setattr(production, "ensure_land_boundary", Mock(return_value=boundary))
    prepare_ahn = Mock(return_value=ahn)
    monkeypatch.setattr(production, "prepare_ahn", prepare_ahn)
    prepare = Mock(wraps=production.prepare_watersysteem)
    monkeypatch.setattr(production, "prepare_watersysteem", prepare)
    calculate = Mock(
        side_effect=lambda *args, **kw: SimpleNamespace(
            merged_path=kw["merged_output_path"]
        )
    )
    monkeypatch.setattr(production, "calculate_afwateringseenheden_tiles", calculate)
    config = None
    if optional_burn:
        source = tmp_path / "burn.gpkg"
        gpd.GeoDataFrame(geometry=[area.geometry], crs=area.crs).to_file(
            source, layer="objects"
        )
        config = BrandlagenConfig(
            (Brandlaag(source, "objects"),), brandwaarde=1, prioriteit=0
        )
    result = production.main(
        store, area=area, run_id="test", offline=True, workers=2, brandlagen=config
    )
    assert (
        result
        == store.processed_data_dir
        / "afwateringseenheden"
        / name
        / "test"
        / "afwateringseenheden.gpkg"
    )
    calculate.assert_called_once()
    assert calculate.call_args.args[0].equals(area.geometry)
    assert calculate.call_args.kwargs["clip_to_area"] is False
    assert calculate.call_args.kwargs["workers"] == 2
    assert calculate.call_args.kwargs["tile_size_m"] == 10000
    assert calculate.call_args.kwargs["tile_buffer_m"] == 2000
    metadata_path = result.parent / "run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["parameters"]["tile_size_m"] == 10000
    assert calculate.call_args.kwargs["brandlagen"] == (config or BrandlagenConfig())
    assert calculate.call_args.kwargs["output_dir"] == (
        result.parent / "berekening" / "tegels"
    )
    assert prepare_ahn.call_args.args[2] == (
        result.parent / "berekening" / "ahn" / "ahn.vrt"
    )
    assert (result.parent / "brandlagen.gpkg").is_file()
    assert (
        result.parent / "berekening" / "watersysteem" / "watersysteem.gpkg"
    ).is_file()
    assert (
        result.parent / "berekening" / "waterlopen_duikers" / "manifest.json"
    ).is_file()
    for old_directory in ("input", "intern", "waternet", "tiles"):
        assert not (result.parent / old_directory).exists()
    if optional_burn:
        assert (
            result.parent / "berekening" / "tegels" / "brandlagen_voorbereid.gpkg"
        ).exists()
    expected = {"38"} if name == "waterschap_38" else {"38", "80"}
    assert (result.parent / "controle.gpkg").is_file()
    assert prepare.call_args.kwargs["duikersifonhevel"].empty
    assert prepare.call_args.kwargs["duiker_tolerance"] == 0.5
    assert prepare.call_args.kwargs["max_aansluitlengte"] is None
    assert set(prepare.call_args.args[0].waterbeheercode) == expected
    context = prepare_ahn.call_args.args[1]
    assert context.covers(box(150000, 400000, 160000, 410000))
    assert context.bounds == (148000, 398000, 162000, 412000)
    for mode in ("resume", "overwrite"):
        production.main(
            store,
            area=area,
            run_id="test",
            offline=True,
            brandlagen=config,
            **{mode: True},
        )
        assert calculate.call_args.kwargs["overwrite"] is (mode == "overwrite")
    if name == "waterschap_38":
        with pytest.raises(ValueError, match="andere instellingen"):
            production.main(
                store,
                area=area,
                run_id="test",
                offline=True,
                resume=True,
                brandlagen=config,
                overige_waterschappen=True,
            )
    if name == "bounds" and not optional_burn:
        original_metadata = metadata_path.read_text(encoding="utf-8")
        metadata["parameters"]["tile_size_m"] = 5000
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        with pytest.raises(ValueError, match="andere instellingen"):
            production.main(store, area=area, run_id="test", offline=True, resume=True)
        metadata_path.write_text(original_metadata, encoding="utf-8")
    # Source changes must not reuse the already prepared network/tile outputs.
    rws["naam"] = "changed source"
    rws.to_file(store.hydamo_dir / "rws_hydamo.gpkg", layer="hydroobject")
    with pytest.raises(ValueError, match="andere bronbestanden"):
        production.main(
            store,
            area=area,
            run_id="test",
            offline=True,
            resume=True,
            brandlagen=config,
        )


def test_bad_brandlagen_stop_before_heavy_sources(tmp_path, monkeypatch):
    store = DataStore(data_dir=tmp_path, _env_file=None)
    area = ProductionArea("alkmaar", box(150100, 400100, 151000, 401000), "EPSG:28992")
    source = tmp_path / "conflict.gpkg"
    gpd.GeoDataFrame(
        {"brandwaarde": [-1, 1], "prioriteit": [0, 0]},
        geometry=[area.geometry] * 2,
        crs=area.crs,
    ).to_file(source, layer="objects")
    monkeypatch.setattr(production, "require_pcraster", Mock())
    monkeypatch.setattr(
        production,
        "ensure_land_boundary",
        lambda *a: pytest.fail("Heavy inputs prepared"),
    )
    with pytest.raises(ValueError, match="opposite signs"):
        production.main(
            store,
            area=area,
            run_id="bad",
            brandlagen=BrandlagenConfig((Brandlaag(source, "objects"),)),
        )


@pytest.mark.parametrize("option", ["duiker_tolerance", "max_aansluitlengte"])
def test_invalid_culvert_options_stop_before_heavy_sources(monkeypatch, option):
    monkeypatch.setattr(production, "require_pcraster", lambda: pytest.fail("Too late"))
    with pytest.raises(ValueError, match="finite and non-negative"):
        production.main(**{option: float("nan")})


@pytest.mark.parametrize(
    "kwargs", [{"eigen_hydamo": "own.gpkg"}, {"overige_waterschappen": True}]
)
def test_authority_options_rejected_before_environment_or_sources(monkeypatch, kwargs):
    monkeypatch.setattr(production, "require_pcraster", lambda: pytest.fail("Too late"))
    with pytest.raises(ValueError, match="waterbeheercode"):
        production.main(area="alkmaar", **kwargs)


def test_own_contract_rejected_before_ahn(tmp_path, monkeypatch):
    store = DataStore(data_dir=tmp_path, _env_file=None)
    for name in ("hydamo.gpkg", "rws_hydamo.gpkg"):
        (store.hydamo_dir / name).write_text("not read before own validation")
    own = tmp_path / "own.gpkg"
    gpd.GeoDataFrame(geometry=[Point(0, 0)], crs=28992).to_file(own, layer="gemaal")
    monkeypatch.setattr(production, "require_pcraster", Mock())
    monkeypatch.setattr(
        production, "ensure_land_boundary", Mock(return_value=tmp_path / "boundary")
    )
    monkeypatch.setattr(
        production,
        "prepare_ahn",
        lambda *a: pytest.fail("AHN prepared before validation"),
    )
    with pytest.raises(ValueError, match="missing required layers"):
        production.main(
            store,
            area=ProductionArea("waterschap_30", box(0, 0, 1, 1), "EPSG:28992"),
            eigen_hydamo=own,
            offline=True,
            run_id="invalid",
        )
