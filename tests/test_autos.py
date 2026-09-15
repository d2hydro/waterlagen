import json
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box

from waterlagen.autos import AUTOS_LAYER, bereken_personenautos_per_vbo, bouw_autos
from waterlagen.vbo_buurt import BAG_VBO_LAYER, CBS_BUURT_OUTPUT_LAYER


def _bag_vbo() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "identificatie": ["vbo-1", "vbo-2", "vbo-3", "vbo-4"],
            "pand_identificatie": ["pand-1", "pand-2", "pand-3", "pand-4"],
            "buurtcode": ["BU00000001", "BU00000001", "BU00000002", "BU99999999"],
        },
        geometry=[Point(1, 1), Point(2, 2), Point(11, 1), Point(31, 1)],
        crs="EPSG:28992",
    )


def _cbs_autos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "buurtcode": ["BU00000001", "BU00000002", "BU00000003"],
            "aantal_woonvbo": [2, 1, 0],
            "personenautos_totaal": [20, 5, 0],
        }
    )


def _write_sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    bag_vbo_path = tmp_path / "bag_vbo.gpkg"
    cbs_buurt_path = tmp_path / "cbs_buurt.gpkg"
    cbs_buurtgegevens_path = tmp_path / "buurtgegevens_2025.json"
    _bag_vbo().to_file(
        bag_vbo_path,
        layer=BAG_VBO_LAYER,
        driver="GPKG",
        index=False,
    )
    gpd.GeoDataFrame(
        _cbs_autos().drop(columns="personenautos_totaal"),
        geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10), box(20, 0, 30, 10)],
        crs="EPSG:28992",
    ).to_file(
        cbs_buurt_path,
        layer=CBS_BUURT_OUTPUT_LAYER,
        driver="GPKG",
        index=False,
    )
    cbs_buurtgegevens_path.write_text(
        json.dumps({"rows": _cbs_autos().to_dict(orient="records")}),
        encoding="utf-8",
    )
    return bag_vbo_path, cbs_buurt_path, cbs_buurtgegevens_path


def test_bereken_personenautos_per_vbo_distributes_values_vectorized(caplog):
    caplog.set_level(logging.WARNING, logger="waterlagen.autos.build")

    result, missing_count, unchecked_buurt_count = bereken_personenautos_per_vbo(
        _bag_vbo(),
        _cbs_autos(),
    )

    assert result.columns.tolist() == [
        "identificatie",
        "pand_identificatie",
        "buurtcode",
        "personenautos_totaal",
        "aantal_woonvbo",
        "personenautos",
        "geometry",
    ]
    assert result.loc[:1, "personenautos"].tolist() == [10.0, 10.0]
    assert result.loc[2, "personenautos"] == 5.0
    assert pd.isna(result.loc[3, "personenautos"])
    assert result.geometry.tolist() == _bag_vbo().geometry.tolist()
    assert result.crs == _bag_vbo().crs
    assert missing_count == 1
    assert unchecked_buurt_count == 1
    assert "1 VBO's have missing required CBS values" in caplog.text
    assert np.isclose(
        result.loc[result["buurtcode"] == "BU00000001", "personenautos"].sum(),
        20,
    )


def test_bereken_personenautos_per_vbo_keeps_zero_woonvbo_as_missing(caplog):
    cbs_autos = _cbs_autos()
    cbs_autos.loc[1, "aantal_woonvbo"] = 0
    caplog.set_level(logging.WARNING, logger="waterlagen.autos.build")

    result, missing_count, _ = bereken_personenautos_per_vbo(_bag_vbo(), cbs_autos)

    assert missing_count == 1
    assert pd.isna(result.loc[2, "personenautos"])
    assert "aantal_woonvbo equal to zero" in caplog.text


def test_bouw_autos_writes_vbo_points_and_reuses_existing_output(tmp_path):
    bag_vbo_path, cbs_buurt_path, cbs_buurtgegevens_path = _write_sources(tmp_path)
    target_path = tmp_path / "autos.gpkg"

    build = bouw_autos(
        bag_vbo_path=bag_vbo_path,
        cbs_buurt_path=cbs_buurt_path,
        cbs_buurtgegevens_path=cbs_buurtgegevens_path,
        target_path=target_path,
    )
    output = gpd.read_file(target_path, layer=AUTOS_LAYER)

    assert build.target_path == target_path
    assert build.vbo_count == 4
    assert build.buurt_count == 3
    assert build.vbos_with_missing_cbs_data == 1
    assert build.buurten_without_control == 1
    assert build.reused is False
    assert output.crs == _bag_vbo().crs
    assert output.geometry.tolist() == _bag_vbo().geometry.tolist()
    assert output.loc[0, "personenautos_totaal"] == 20
    assert output.loc[0, "aantal_woonvbo"] == 2
    assert output.loc[0, "personenautos"] == 10

    reused = bouw_autos(
        bag_vbo_path=tmp_path / "missing-bag.gpkg",
        cbs_buurt_path=tmp_path / "missing-cbs.gpkg",
        cbs_buurtgegevens_path=tmp_path / "missing-cbs.json",
        target_path=target_path,
        overwrite=False,
    )

    assert reused.reused is True
    assert reused.vbo_count == 4
    assert reused.buurt_count == 3
