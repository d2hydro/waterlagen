import logging
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from waterlagen.vbo_buurt import (
    BAG_VBO_LAYER,
    CBS_BUURT_OUTPUT_LAYER,
    HILBERT_COLUMN,
    BuurtKoppelingError,
    bouw_vbo_buurt,
    koppel_features_aan_buurten,
    selecteer_woonverblijfsobjecten,
    sorteer_op_hilbert,
)


def _verblijfsobjecten() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "identificatie": ["vbo-1", "vbo-2", "vbo-3", "vbo-4"],
            "pand_identificatie": ["pand-1", "pand-2", "pand-3", "pand-4"],
            "status": [
                "Verblijfsobject in gebruik",
                "Verblijfsobject in gebruik",
                "Verblijfsobject buiten gebruik",
                "Verblijfsobject in gebruik",
            ],
            "gebruiksdoel": [
                "woonfunctie,kantoorfunctie",
                "winkelfunctie",
                "woonfunctie",
                "kantoorfunctie,woonfunctie",
            ],
        },
        geometry=[
            Point(100_001, 400_001),
            Point(100_002, 400_002),
            Point(100_003, 400_003),
            Point(110_001, 400_001),
        ],
        crs="EPSG:28992",
    )


def _buurten(*, overlapping: bool = False) -> gpd.GeoDataFrame:
    geometries = [
        box(100_000, 400_000, 100_010, 400_010),
        box(110_000, 400_000, 110_010, 400_010),
        box(120_000, 400_000, 120_010, 400_010),
    ]
    codes = ["BU00000001", "BU00000002", "BU00000003"]
    if overlapping:
        geometries = [
            box(100_000, 400_000, 100_010, 400_010),
            box(100_000, 400_000, 100_010, 400_010),
        ]
        codes = ["BU00000001", "BU00000002"]
    return gpd.GeoDataFrame(
        {"buurtcode": codes},
        geometry=geometries,
        crs="EPSG:28992",
    )


def _write_sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    bag_path = tmp_path / "bag.gpkg"
    _verblijfsobjecten().to_file(
        bag_path,
        layer="verblijfsobject",
        driver="GPKG",
        index=False,
    )
    buurtkaart_path = tmp_path / "wijkenbuurten.gpkg"
    _buurten().to_file(
        buurtkaart_path,
        layer="buurten",
        driver="GPKG",
        index=False,
    )
    cbs_buurtgegevens_path = tmp_path / "buurtgegevens_2025.json"
    cbs_buurtgegevens_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "buurtcode": "BU00000001",
                        "aantal_inwoners": 100,
                        "aantal_huishoudens": 50,
                        "personenautos_totaal": 40,
                    },
                    {
                        "buurtcode": "BU00000002",
                        "aantal_inwoners": 200,
                        "aantal_huishoudens": 90,
                        "personenautos_totaal": 80,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return bag_path, buurtkaart_path, cbs_buurtgegevens_path


def test_selecteer_woonverblijfsobjecten_keeps_multi_function_vbos():
    selected = selecteer_woonverblijfsobjecten(_verblijfsobjecten())

    assert selected["identificatie"].tolist() == ["vbo-1", "vbo-4"]
    assert selected.geometry.tolist() == [
        Point(100_001, 400_001),
        Point(110_001, 400_001),
    ]
    assert selected["status"].eq("Verblijfsobject in gebruik").all()


def test_sorteer_op_hilbert_keeps_vbo_attributes_geometries_and_crs():
    features = gpd.GeoDataFrame(
        {
            "identificatie": ["vbo-1", "vbo-2", "vbo-3"],
            "buurtcode": ["BU00000001", "BU00000002", "BU00000003"],
        },
        geometry=[
            Point(200_000, 400_000),
            Point(10_000, 500_000),
            Point(100_000, 300_000),
        ],
        crs="EPSG:28992",
    )

    result = sorteer_op_hilbert(features)

    assert pd.api.types.is_integer_dtype(result[HILBERT_COLUMN])
    assert result[HILBERT_COLUMN].notna().all()
    assert result[HILBERT_COLUMN].is_monotonic_increasing
    assert set(result["identificatie"]) == set(features["identificatie"])
    assert set(result.geometry) == set(features.geometry)
    assert result.crs == features.crs


def test_koppel_features_aan_buurten_assigns_one_code_and_preserves_crs():
    features = selecteer_woonverblijfsobjecten(_verblijfsobjecten())

    result = koppel_features_aan_buurten(
        features,
        _buurten(),
        feature_id_column="identificatie",
    )

    assert result["buurtcode"].tolist() == ["BU00000001", "BU00000002"]
    assert result.crs == "EPSG:28992"
    assert result.geometry.tolist() == features.geometry.tolist()


def test_koppel_features_aan_buurten_reports_unmatched_features(caplog):
    features = gpd.GeoDataFrame(
        {"identificatie": ["vbo-1"]},
        geometry=[Point(30, 30)],
        crs="EPSG:28992",
    )
    caplog.set_level(logging.WARNING, logger="waterlagen.vbo_buurt.build")

    with pytest.raises(BuurtKoppelingError, match="1 unmatched"):
        koppel_features_aan_buurten(
            features,
            _buurten(),
            feature_id_column="identificatie",
        )

    assert "1 features have no CBS buurt match" in caplog.text


def test_koppel_features_aan_buurten_reports_multiple_matches(caplog):
    features = gpd.GeoDataFrame(
        {"identificatie": ["vbo-1"]},
        geometry=[Point(100_001, 400_001)],
        crs="EPSG:28992",
    )
    caplog.set_level(logging.WARNING, logger="waterlagen.vbo_buurt.build")

    with pytest.raises(BuurtKoppelingError, match="1 multiple matches"):
        koppel_features_aan_buurten(
            features,
            _buurten(overlapping=True),
            feature_id_column="identificatie",
        )

    assert "1 features have multiple CBS buurt matches" in caplog.text


def test_bouw_vbo_buurt_writes_separate_bag_vbo_and_cbs_buurt_outputs(tmp_path):
    bag_path, buurtkaart_path, cbs_buurtgegevens_path = _write_sources(tmp_path)
    bag_vbo_path = tmp_path / "bag_vbo.gpkg"
    cbs_buurt_path = tmp_path / "cbs_buurt.gpkg"

    result = bouw_vbo_buurt(
        bag_path=bag_path,
        buurtkaart_path=buurtkaart_path,
        cbs_buurtgegevens_path=cbs_buurtgegevens_path,
        bag_vbo_path=bag_vbo_path,
        cbs_buurt_path=cbs_buurt_path,
    )
    bag_vbo = gpd.read_file(bag_vbo_path, layer=BAG_VBO_LAYER)
    cbs_buurt = gpd.read_file(cbs_buurt_path, layer=CBS_BUURT_OUTPUT_LAYER)

    assert result.source_vbo_count == 4
    assert result.selected_woonvbo_count == 2
    assert result.buurt_count == 2
    assert result.bag_vbo_path == bag_vbo_path
    assert result.cbs_buurt_path == cbs_buurt_path
    assert bag_vbo.columns.tolist() == [
        "identificatie",
        "pand_identificatie",
        "status",
        "gebruiksdoel",
        "buurtcode",
        "_hilbert",
        "geometry",
    ]
    assert "aantal_woonvbo" not in bag_vbo.columns
    assert bag_vbo["identificatie"].tolist() == ["vbo-1", "vbo-4"]
    assert bag_vbo["buurtcode"].notna().all()
    assert pd.api.types.is_integer_dtype(bag_vbo[HILBERT_COLUMN])
    assert bag_vbo[HILBERT_COLUMN].notna().all()
    assert bag_vbo[HILBERT_COLUMN].is_monotonic_increasing
    assert bag_vbo.crs == "EPSG:28992"
    assert bag_vbo.geometry.tolist() == [
        Point(100_001, 400_001),
        Point(110_001, 400_001),
    ]

    assert cbs_buurt.columns.tolist() == [
        "buurtcode",
        "aantal_inwoners",
        "aantal_huishoudens",
        "personenautos_totaal",
        "aantal_woonvbo",
        "geometry",
    ]
    assert cbs_buurt["aantal_inwoners"].tolist()[:2] == [100, 200]
    assert cbs_buurt["aantal_huishoudens"].tolist()[:2] == [50, 90]
    assert cbs_buurt["personenautos_totaal"].tolist()[:2] == [40, 80]
    assert pd.isna(cbs_buurt.loc[2, "aantal_inwoners"])
    assert pd.isna(cbs_buurt.loc[2, "aantal_huishoudens"])
    assert pd.isna(cbs_buurt.loc[2, "personenautos_totaal"])
    assert cbs_buurt["aantal_woonvbo"].tolist() == [1, 1, 0]
    assert cbs_buurt.crs == "EPSG:28992"
    assert cbs_buurt.geometry.tolist() == _buurten().geometry.tolist()


def test_bouw_vbo_buurt_reuses_existing_output_without_reading_sources(tmp_path):
    bag_path, buurtkaart_path, cbs_buurtgegevens_path = _write_sources(tmp_path)
    bag_vbo_path = tmp_path / "bag_vbo.gpkg"
    cbs_buurt_path = tmp_path / "cbs_buurt.gpkg"
    bouw_vbo_buurt(
        bag_path=bag_path,
        buurtkaart_path=buurtkaart_path,
        cbs_buurtgegevens_path=cbs_buurtgegevens_path,
        bag_vbo_path=bag_vbo_path,
        cbs_buurt_path=cbs_buurt_path,
    )

    result = bouw_vbo_buurt(
        bag_path=tmp_path / "missing-bag.gpkg",
        buurtkaart_path=tmp_path / "missing-buurten.gpkg",
        cbs_buurtgegevens_path=tmp_path / "missing-cbs.json",
        bag_vbo_path=bag_vbo_path,
        cbs_buurt_path=cbs_buurt_path,
        overwrite=False,
    )

    assert result.reused is True
    assert result.source_vbo_count is None
    assert result.selected_woonvbo_count == 2


def test_bouw_vbo_buurt_rebuilds_a_cached_cbs_buurt_without_personenautos(
    tmp_path,
):
    bag_path, buurtkaart_path, cbs_buurtgegevens_path = _write_sources(tmp_path)
    bag_vbo_path = tmp_path / "bag_vbo.gpkg"
    cbs_buurt_path = tmp_path / "cbs_buurt.gpkg"
    bouw_vbo_buurt(
        bag_path=bag_path,
        buurtkaart_path=buurtkaart_path,
        cbs_buurtgegevens_path=cbs_buurtgegevens_path,
        bag_vbo_path=bag_vbo_path,
        cbs_buurt_path=cbs_buurt_path,
    )
    cached_buurten = gpd.read_file(cbs_buurt_path, layer=CBS_BUURT_OUTPUT_LAYER)
    cached_buurten.drop(columns="personenautos_totaal").to_file(
        cbs_buurt_path,
        layer=CBS_BUURT_OUTPUT_LAYER,
        driver="GPKG",
        index=False,
    )

    result = bouw_vbo_buurt(
        bag_path=bag_path,
        buurtkaart_path=buurtkaart_path,
        cbs_buurtgegevens_path=cbs_buurtgegevens_path,
        bag_vbo_path=bag_vbo_path,
        cbs_buurt_path=cbs_buurt_path,
        overwrite=False,
    )

    cbs_buurt = gpd.read_file(cbs_buurt_path, layer=CBS_BUURT_OUTPUT_LAYER)
    assert result.reused is False
    assert cbs_buurt["personenautos_totaal"].tolist()[:2] == [40, 80]
