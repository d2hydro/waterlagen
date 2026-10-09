from types import SimpleNamespace

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from waterlagen import _cbs_production as production
from waterlagen.areas import ProductionArea
from waterlagen.datastore import DataStore


@pytest.mark.parametrize("dataset", ["inwoners", "autos"])
def test_production_prepares_and_reuses_shared_sources(dataset, tmp_path, monkeypatch):
    import waterlagen.autos
    import waterlagen.inwoners
    from waterlagen.autos import productie as autos
    from waterlagen.inwoners import productie as inwoners

    store = DataStore(data_dir=tmp_path, _env_file=None)
    area = ProductionArea("nederland", box(0, 0, 10, 10), "EPSG:28992")
    downloads = []
    builds = []

    def download(name, path, **kwargs):
        downloads.append((name, kwargs["overwrite"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(len(downloads)))

    monkeypatch.setattr(
        production,
        "download_bag_light",
        lambda **kw: download("bag", store.bag_dir / "bag-light.gpkg", **kw),
    )
    monkeypatch.setattr(
        production,
        "download_wijk_buurtkaart_2025",
        lambda **kw: download(
            "buurt",
            production.wijk_buurtkaart_2025_path(
                download_dir=store.administratieve_gebieden_dir
            ),
            **kw,
        ),
    )
    monkeypatch.setattr(
        production,
        "download_buurtgegevens_2025",
        lambda **kw: download(
            "cbs", production.buurtgegevens_2025_path(store.cbs_dir), **kw
        ),
    )

    def prepare(**kwargs):
        builds.append(kwargs)
        store.bag_vbo_path.parent.mkdir(parents=True, exist_ok=True)
        store.bag_vbo_path.write_text("prepared bag")
        store.cbs_buurt_path.write_text("prepared buurten")

    results = []

    def build(**kwargs):
        results.append(kwargs)
        kwargs["target_path"].write_text("result")
        return SimpleNamespace(target_path=kwargs["target_path"])

    monkeypatch.setattr(production, "bouw_vbo_buurt", prepare)
    monkeypatch.setattr(waterlagen.autos, "bouw_autos", build)
    monkeypatch.setattr(waterlagen.inwoners, "bouw_inwoners", build)
    workflow = autos.main if dataset == "autos" else inwoners.main
    result = workflow(store, area=area, run_id="first")
    assert (
        result
        == store.processed_data_dir
        / dataset
        / "nederland"
        / "first"
        / f"{dataset}.gpkg"
    )
    assert downloads == [("bag", False), ("buurt", False), ("cbs", False)]
    workflow(store, area=area, run_id="first", resume=True, offline=True)
    workflow(store, area=area, run_id="first", overwrite=True)
    assert len(downloads) == 3
    assert len(builds) == 1
    assert results[-1]["overwrite"] is True
    workflow(store, area=area, run_id="fresh", refresh_sources=True)
    assert downloads[3:] == [("bag", True), ("buurt", True), ("cbs", True)]
    assert len(builds) == 2
    with pytest.raises(ValueError, match="bestaat al"):
        workflow(store, area="nederland", run_id="fresh", refresh_sources=True)
    assert len(downloads) == 6


def test_area_keeps_complete_buurt_and_vbo_context(tmp_path):
    buurten = gpd.GeoDataFrame(
        {"buurtcode": ["A", "B"], "aantal_inwoners": [100, 200]},
        geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10)],
        crs=28992,
    )
    bag = gpd.GeoDataFrame(
        {"buurtcode": ["A", "A", "B"], "id": [1, 2, 3]},
        geometry=[Point(1, 1), Point(9, 9), Point(12, 2)],
        crs=28992,
    )
    bag_path, buurt_path = tmp_path / "bag.gpkg", tmp_path / "buurt.gpkg"
    bag.to_file(bag_path, layer=production.BAG_VBO_LAYER)
    buurten.to_file(buurt_path, layer=production.CBS_BUURT_OUTPUT_LAYER)
    area = ProductionArea("alkmaar", box(0, 0, 2, 2), "EPSG:28992")
    bag_output, buurt_output = production.select_buurt_context(
        bag_path, buurt_path, area, tmp_path / "selection"
    )
    selected = gpd.read_file(bag_output)
    assert selected.id.tolist() == [1, 2]
    assert selected.geometry.iloc[1].equals(Point(9, 9))
    assert gpd.read_file(buurt_output).aantal_inwoners.tolist() == [100]
