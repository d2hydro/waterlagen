from dataclasses import replace

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from waterlagen.functioneel_landgebruik.kassen_rwzi_drinkwater import (
    SpecialBuildingSources,
    apply_special_building_classes,
)
from waterlagen.functioneel_landgebruik.landgebruikstabel import load_landuse_table


def buildings(geometries):
    count = len(geometries)
    return gpd.GeoDataFrame(
        {
            "identificatie": [f"pand-{i}" for i in range(count)],
            "lgb_koppeling_id": ["BAG-033"] * count,
            "lgb_omschrijving": ["overige"] * count,
            "lgb_code_binnendijks": pd.array([33] * count, dtype="Int64"),
            "lgb_code_buitendijks": pd.array([161] * count, dtype="Int64"),
            "klasse_status": ["ingedeeld"] * count,
            "reden_klasse": ["BAG"] * count,
            "alle_bag_gebruiksdoelen": ["overige gebruiksfunctie"] * count,
        },
        geometry=geometries,
        crs="EPSG:28992",
    )


def write_top(path, geometries=(), values=()):
    gpd.GeoDataFrame(
        {"typegebouw": list(values), "lokaalid": [f"t{i}" for i in range(len(values))]},
        geometry=list(geometries),
        crs="EPSG:28992",
    ).to_file(path, layer="top10nl_gebouw_vlak", driver="GPKG")


def test_greenhouse_exact_tokens_majority_overlap_and_csv_codes(tmp_path):
    path = tmp_path / "top.gpkg"
    write_top(
        path,
        [box(-1, -1, 9, 11), box(20, 0, 30, 10)],
        ["kas, warenhuis|school", "kasteel"],
    )
    panden = buildings([box(0, 0, 10, 10), box(8, 0, 18, 10), box(20, 0, 30, 10)])
    table = load_landuse_table()
    rows = tuple(
        replace(row, inside=44, outside=172) if "TOP10NL-BAG-001" in row.ids else row
        for row in table.rows
    )
    result = apply_special_building_classes(
        panden, SpecialBuildingSources(path), table=replace(table, rows=rows)
    )
    assert result.lgb_code_binnendijks.tolist() == [44, 33, 33]
    assert result.lgb_code_buitendijks.tolist() == [172, 161, 161]
    assert result.basis_lgb_code_binnendijks.tolist() == [33, 33, 33]
    assert result.geometry.equals(panden.geometry)
    assert "bron ontbreekt" in result.iloc[0].controle_bijzondere_bronnen


def test_rwzi_active_point_outside_building_extent_and_drinking_water(tmp_path):
    top, rwzi, drinking = [
        tmp_path / f"{name}.gpkg" for name in ["top", "rwzi", "drinking"]
    ]
    write_top(top)
    gpd.GeoDataFrame(
        {
            "typefunctioneelgebied": ["zuiveringsinstallatie"] * 2,
            "lokaalid": ["active", "closed"],
        },
        geometry=[box(-10, -10, 100, 20), box(100, -10, 200, 20)],
        crs="EPSG:28992",
    ).to_file(top, layer="top10nl_functioneel_gebied_vlak", driver="GPKG")
    gpd.GeoDataFrame(
        {"typefunctioneelgebied": [], "lokaalid": []}, geometry=[], crs="EPSG:28992"
    ).to_file(top, layer="top10nl_functioneel_gebied_multivlak", driver="GPKG")
    gpd.GeoDataFrame(
        {"status": ["in gebruik", "gerealiseerd"]},
        geometry=[Point(90, 10), Point(110, 10)],
        crs="EPSG:28992",
    ).to_file(rwzi, layer="rwzi", driver="GPKG")
    gpd.GeoDataFrame(geometry=[box(210, -5, 230, 20)], crs="EPSG:28992").to_file(
        drinking, layer="drinkwaterproductieterrein", driver="GPKG"
    )
    config = SpecialBuildingSources(top, rwzi_gpkg=rwzi, drinking_water_gpkg=drinking)
    panden = buildings([box(0, 0, 10, 10), box(120, 0, 130, 10), box(215, 0, 225, 10)])
    result = apply_special_building_classes(panden, config)
    assert result.lgb_code_binnendijks.tolist() == [36, 33, 37]
    # Tile invariance: the active status point is outside this small building extent.
    single = apply_special_building_classes(panden.iloc[:1], config)
    assert single.iloc[0].lgb_code_binnendijks == 36
    with pytest.raises(ValueError, match="bedrijfsstatus"):
        apply_special_building_classes(
            panden, replace(config, rwzi_status_column="missing")
        )


def test_special_conflict_and_crs_mismatch(tmp_path):
    top, drinking = tmp_path / "top.gpkg", tmp_path / "drinking.gpkg"
    write_top(top, [box(0, 0, 10, 10)], ["kas, warenhuis"])
    gpd.GeoDataFrame(geometry=[box(-1, -1, 11, 11)], crs="EPSG:28992").to_file(
        drinking, layer="drinkwaterproductieterrein", driver="GPKG"
    )
    config = SpecialBuildingSources(top, drinking_water_gpkg=drinking)
    result = apply_special_building_classes(buildings([box(0, 0, 10, 10)]), config)
    assert pd.isna(result.iloc[0].lgb_code_binnendijks)
    assert result.iloc[0].klasse_status == "nog te beoordelen"
    with pytest.raises(ValueError, match="CRS"):
        apply_special_building_classes(
            buildings([box(0, 0, 10, 10)]).to_crs(4326), config
        )
