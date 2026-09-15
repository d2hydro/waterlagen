import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from shapely.geometry import Point, box

from waterlagen.inwoners import (
    INWONERS_LAYER,
    bereken_inwoners_per_vbo,
    bouw_inwoners,
)
from waterlagen.vbo_buurt import BAG_VBO_LAYER, CBS_BUURT_OUTPUT_LAYER


def _bag_vbo() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "identificatie": ["vbo-1", "vbo-2", "vbo-3", "vbo-4"],
            "pand_identificatie": ["pand-1", "pand-2", "pand-3", "pand-4"],
            "buurtcode": ["BU00000001", "BU00000001", "BU00000002", "BU99999999"],
            "_hilbert": [1, 2, 3, 4],
        },
        geometry=[Point(1, 1), Point(2, 2), Point(11, 1), Point(31, 1)],
        crs="EPSG:28992",
    )


def _cbs_buurten() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "buurtcode": ["BU00000001", "BU00000002", "BU00000003"],
            "aantal_inwoners": [100, 30, 0],
            "aantal_huishoudens": [4, 3, 0],
            "aantal_woonvbo": [2, 1, 0],
        },
        geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10), box(20, 0, 30, 10)],
        crs="EPSG:28992",
    )


def _write_sources(tmp_path: Path) -> tuple[Path, Path]:
    bag_vbo_path = tmp_path / "bag_vbo.gpkg"
    cbs_buurt_path = tmp_path / "cbs_buurt.gpkg"
    _bag_vbo().to_file(
        bag_vbo_path,
        layer=BAG_VBO_LAYER,
        driver="GPKG",
        index=False,
    )
    _cbs_buurten().to_file(
        cbs_buurt_path,
        layer=CBS_BUURT_OUTPUT_LAYER,
        driver="GPKG",
        index=False,
    )
    return bag_vbo_path, cbs_buurt_path


def test_bereken_inwoners_per_vbo_keeps_two_methods_and_missing_cbs_values(caplog):
    caplog.set_level(logging.WARNING, logger="waterlagen.inwoners.build")

    result, missing_count, unchecked_buurt_count = bereken_inwoners_per_vbo(
        _bag_vbo(),
        _cbs_buurten().drop(columns="geometry"),
    )

    assert result.columns.tolist() == [
        "identificatie",
        "pand_identificatie",
        "buurtcode",
        "aantal_inwoners",
        "aantal_huishoudens",
        "aantal_woonvbo",
        "inwoners_obv_huishoudens",
        "inwoners_obv_woonvbo",
        "_hilbert",
        "geometry",
    ]
    assert result.loc[:1, "inwoners_obv_huishoudens"].tolist() == [25.0, 25.0]
    assert result.loc[:1, "inwoners_obv_woonvbo"].tolist() == [50.0, 50.0]
    assert result.loc[2, "inwoners_obv_huishoudens"] == 10.0
    assert result.loc[2, "inwoners_obv_woonvbo"] == 30.0
    assert pd.isna(result.loc[3, "inwoners_obv_huishoudens"])
    assert pd.isna(result.loc[3, "inwoners_obv_woonvbo"])
    assert result.geometry.tolist() == _bag_vbo().geometry.tolist()
    assert result.crs == _bag_vbo().crs
    assert result["_hilbert"].tolist() == [1, 2, 3, 4]
    assert result["_hilbert"].is_monotonic_increasing
    assert missing_count == 1
    assert unchecked_buurt_count == 1
    assert "1 VBO's have missing required CBS values" in caplog.text

    buurt_1 = result.loc[result["buurtcode"] == "BU00000001"]
    assert np.isclose(buurt_1["inwoners_obv_woonvbo"].sum(), 100)
    assert np.isclose(buurt_1["inwoners_obv_huishoudens"].sum(), 100 * 2 / 4)


def test_bereken_inwoners_per_vbo_keeps_zero_denominator_as_missing(caplog):
    cbs_buurten = _cbs_buurten().drop(columns="geometry")
    cbs_buurten.loc[1, "aantal_huishoudens"] = 0
    caplog.set_level(logging.WARNING, logger="waterlagen.inwoners.build")

    result, missing_count, _ = bereken_inwoners_per_vbo(_bag_vbo(), cbs_buurten)

    assert missing_count == 1
    assert pd.isna(result.loc[2, "inwoners_obv_huishoudens"])
    assert result.loc[2, "inwoners_obv_woonvbo"] == 30.0
    assert "zero CBS denominator" in caplog.text


def test_bouw_inwoners_writes_vbo_points_and_reuses_existing_output(tmp_path):
    bag_vbo_path, cbs_buurt_path = _write_sources(tmp_path)
    target_path = tmp_path / "inwoners.gpkg"
    geoparquet_path = tmp_path / "inwoners.parquet"

    build = bouw_inwoners(
        bag_vbo_path=bag_vbo_path,
        cbs_buurt_path=cbs_buurt_path,
        target_path=target_path,
        geoparquet_path=geoparquet_path,
        write_geoparquet=True,
    )
    output = gpd.read_file(target_path, layer=INWONERS_LAYER)
    parquet_output = gpd.read_parquet(geoparquet_path)

    assert build.target_path == target_path
    assert build.vbo_count == 4
    assert build.buurt_count == 3
    assert build.vbos_with_missing_cbs_data == 1
    assert build.buurten_without_woonvbo_control == 1
    assert build.reused is False
    assert build.geoparquet_path == geoparquet_path
    assert output.crs == _bag_vbo().crs
    assert output.geometry.tolist() == _bag_vbo().geometry.tolist()
    assert output["_hilbert"].tolist() == [1, 2, 3, 4]
    assert output["_hilbert"].is_monotonic_increasing
    assert output.loc[0, "aantal_inwoners"] == 100
    assert output.loc[0, "aantal_huishoudens"] == 4
    assert output.loc[0, "aantal_woonvbo"] == 2
    assert parquet_output["_hilbert"].tolist() == [1, 2, 3, 4]
    assert parquet_output.geometry.tolist() == _bag_vbo().geometry.tolist()
    assert parquet_output.crs == _bag_vbo().crs
    assert pq.read_metadata(geoparquet_path).num_row_groups == 1

    reused = bouw_inwoners(
        bag_vbo_path=tmp_path / "missing-bag.gpkg",
        cbs_buurt_path=tmp_path / "missing-cbs.gpkg",
        target_path=target_path,
        geoparquet_path=geoparquet_path,
        overwrite=False,
        write_geoparquet=True,
    )

    assert reused.reused is True
    assert reused.vbo_count == 4
    assert reused.buurt_count == 3
    assert reused.geoparquet_path == geoparquet_path
