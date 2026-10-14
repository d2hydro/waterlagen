from types import SimpleNamespace
from unittest.mock import Mock

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, box

from waterlagen.afwateringseenheden import Brandlaag, BrandlagenConfig
from waterlagen.afwateringseenheden import productie as production
from waterlagen.areas import ProductionArea
from waterlagen.datastore import DataStore


@pytest.mark.parametrize("name", ["nederland", "alkmaar", "waterschap_38"])
@pytest.mark.parametrize("optional_burn", [False, True])
def test_one_area_product_with_full_tiles_and_all_authorities(
    tmp_path, monkeypatch, name, optional_burn
):
    store = DataStore(data_dir=tmp_path, _env_file=None)
    area = ProductionArea(name, box(150100, 400100, 151000, 401000), "EPSG:28992")
    hydamo = store.hydamo_dir / "hydamo.gpkg"
    boundary = tmp_path / "boundary.gpkg"
    ahn = tmp_path / "ahn.vrt"
    for path in (hydamo, boundary, ahn):
        path.write_text("existing")
    ahn.write_text("<VRTDataset />")
    hydro = gpd.GeoDataFrame(
        {production.CATEGORIE_OPPERVLAKTEWATER_COLUMN: ["primair", "secundair"]},
        geometry=[LineString([(150000, 400000), (151000, 401000)])] * 2,
        crs=28992,
    )
    points = gpd.GeoDataFrame(geometry=[Point(150000, 400000)], crs=28992)
    monkeypatch.setattr(production, "require_pcraster", Mock())
    monkeypatch.setattr(production, "ensure_land_boundary", Mock(return_value=boundary))
    prepare_ahn = Mock(return_value=ahn)
    monkeypatch.setattr(production, "prepare_ahn", prepare_ahn)
    monkeypatch.setattr(production, "read_hydroobjecten", Mock(return_value=hydro))
    read_points = Mock(return_value=points)
    monkeypatch.setattr(production, "read_puntobjecten", read_points)
    monkeypatch.setattr(production, "prepare_watersysteem", Mock(return_value=object()))
    monkeypatch.setattr(
        production, "write_watersysteem", lambda **kw: kw["output_path"]
    )
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
    assert calculate.call_args.kwargs["brandlagen"] == config
    if optional_burn:
        assert (result.parent / "tiles" / "brandlagen.gpkg").exists()
    assert "waterbeheercodes" not in read_points.call_args.kwargs
    context = prepare_ahn.call_args.args[1]
    assert context.covers(box(150000, 400000, 160000, 410000))
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
