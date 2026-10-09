import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import pytest
from shapely.geometry import Point, box


def _load_script():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "statistiek_inwoners_autos.py"
    )
    spec = importlib.util.spec_from_file_location(
        "statistiek_inwoners_autos", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("explicit_paths", [False, True])
def test_script_logs_cbs_and_derived_totals(tmp_path, caplog, explicit_paths):
    script = _load_script()
    cbs_buurt_path = tmp_path / "cbs_buurt.gpkg"
    inwoners_path = tmp_path / "inwoners.gpkg"
    autos_path = tmp_path / "autos.gpkg"
    gpd.GeoDataFrame(
        {
            "aantal_inwoners": [100, 50],
            "personenautos_totaal": [20, 10],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:28992",
    ).to_file(cbs_buurt_path, layer="cbs_buurt", driver="GPKG", index=False)
    gpd.GeoDataFrame(
        {
            "inwoners_obv_huishoudens": [40.0, 80.0],
            "inwoners_obv_woonvbo": [50.0, 100.0],
        },
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:28992",
    ).to_file(inwoners_path, layer="inwoners", driver="GPKG", index=False)
    gpd.GeoDataFrame(
        {"personenautos": [12.0, 18.0]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:28992",
    ).to_file(autos_path, layer="autos", driver="GPKG", index=False)
    data_store = SimpleNamespace(
        data_dir=tmp_path,
        cbs_buurt_path=cbs_buurt_path,
        inwoners_path=inwoners_path,
        autos_path=autos_path,
    )
    caplog.set_level(logging.INFO, logger="statistiek_inwoners_autos")

    if explicit_paths:
        data_store.inwoners_path = tmp_path / "missing_inwoners.gpkg"
        data_store.autos_path = tmp_path / "missing_autos.gpkg"
        statistieken = script.main(
            data_store=data_store, inwoners_path=inwoners_path, autos_path=autos_path
        )
    else:
        statistieken = script.main(data_store=data_store)

    assert statistieken.cbs_aantal_inwoners == 150
    assert statistieken.inwoners_obv_huishoudens == 120
    assert statistieken.inwoners_obv_woonvbo == 150
    assert statistieken.cbs_personenautos_totaal == 30
    assert statistieken.personenautos == 30
    assert "CBS aantal_inwoners: 150" in caplog.text
    assert "Som inwoners_obv_huishoudens: 120" in caplog.text
    assert "Som inwoners_obv_woonvbo: 150" in caplog.text
    assert "CBS personenautos_totaal: 30" in caplog.text
    assert "Som personenautos: 30" in caplog.text
