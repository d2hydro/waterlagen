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


def test_rwzi_point_outside_building_extent_and_drinking_water(tmp_path):
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
    assert result.lgb_code_binnendijks.tolist() == [36, 36, 37]
    assert result.lgb_code_buitendijks.tolist() == [164, 164, 165]
    assert result.iloc[0].lgb_omschrijving == "RWZI (gebouw op RWZI-terrein)"
    # Tile invariance: the confirming point is outside this small building extent.
    single = apply_special_building_classes(panden.iloc[:1], config)
    assert single.iloc[0].lgb_code_binnendijks == 36
    legacy = apply_special_building_classes(
        panden, replace(config, rwzi_status_column="missing")
    )
    assert legacy.lgb_code_binnendijks.tolist() == [36, 36, 37]


@pytest.mark.parametrize("feature", [Point(0, 5), box(-2, 4, 1, 6)])
def test_damo_terrain_validation_and_building_boundaries(tmp_path, feature):
    top, damo = tmp_path / "top.gpkg", tmp_path / "damo.gpkg"
    write_top(top)
    gpd.GeoDataFrame(
        {
            "typefunctioneelgebied": [
                "zuiveringsinstallatie",
                "zuiveringsinstallatie",
                "zuiveringsinstallatie|overig",
            ]
        },
        geometry=[box(0, 0, 10, 10), box(20, 0, 30, 10), box(40, 0, 50, 10)],
        crs="EPSG:28992",
    ).to_file(top, layer="top10nl_functioneel_gebied_vlak", driver="GPKG")
    # No status column or multivlak layer is needed; duplicate confirmations must not duplicate BAG.
    gpd.GeoDataFrame(
        {"typefunctioneelgebied": ["zuiveringsinstallatie"]},
        geometry=[box(40, 0, 50, 10)],
        crs="EPSG:28992",
    ).to_file(top, layer="top10nl_functioneel_gebied_multivlak", driver="GPKG")
    gpd.GeoDataFrame(
        geometry=[feature, feature, Point(45, 5)], crs="EPSG:28992"
    ).to_file(damo, layer="rwzi", driver="GPKG")
    panden = buildings(
        [
            box(1, 1, 3, 3),  # Internal representative point.
            box(10, 2, 12, 4),  # Touches terrain only.
            box(9, 2, 11, 4),  # Representative point on boundary.
            box(9, 2, 13, 4),  # Positive overlap but representative point outside.
            box(8, 2, 11, 4),  # Representative point inside despite partial overlap.
            box(21, 1, 23, 3),  # Unconfirmed terrain.
            box(41, 1, 43, 3),  # Wrong TOP10NL value despite DAMO confirmation.
        ]
    )
    result = apply_special_building_classes(
        panden, SpecialBuildingSources(top, rwzi_gpkg=damo)
    )
    assert result.lgb_code_binnendijks.tolist() == [36, 33, 33, 33, 36, 33, 33]
    assert result.lgb_code_buitendijks.tolist() == [164, 161, 161, 161, 164, 161, 161]
    assert result.geometry.equals(panden.geometry)
    assert result.basis_lgb_code_binnendijks.tolist() == [33] * len(panden)
    assert len(result) == len(panden)
    with pytest.raises(ValueError, match="CRS"):
        apply_special_building_classes(
            panden.to_crs(4326), SpecialBuildingSources(top, rwzi_gpkg=damo)
        )


@pytest.mark.parametrize("conflict", ["kas", "drinkwater"])
def test_rwzi_does_not_silently_replace_other_special_class(tmp_path, conflict):
    top, damo, drinking = [
        tmp_path / f"{name}.gpkg" for name in ["top", "damo", "drinking"]
    ]
    footprint = box(1, 1, 3, 3)
    write_top(
        top,
        [footprint] if conflict == "kas" else [],
        ["kas, warenhuis"] if conflict == "kas" else [],
    )
    gpd.GeoDataFrame(
        {"typefunctioneelgebied": ["zuiveringsinstallatie"]},
        geometry=[box(0, 0, 10, 10)],
        crs="EPSG:28992",
    ).to_file(top, layer="top10nl_functioneel_gebied_vlak", driver="GPKG")
    gpd.GeoDataFrame(geometry=[Point(5, 5)], crs="EPSG:28992").to_file(
        damo, layer="rwzi", driver="GPKG"
    )
    gpd.GeoDataFrame(geometry=[box(0, 0, 10, 10)], crs="EPSG:28992").to_file(
        drinking, layer="drinkwaterproductieterrein", driver="GPKG"
    )
    result = apply_special_building_classes(
        buildings([footprint]),
        SpecialBuildingSources(
            top,
            rwzi_gpkg=damo,
            drinking_water_gpkg=drinking if conflict == "drinkwater" else None,
        ),
    )
    assert pd.isna(result.iloc[0].lgb_code_binnendijks)
    assert result.iloc[0].klasse_status == "nog te beoordelen"
    assert "TOP10NL-NGR-BAG-001" in result.iloc[0].bijzondere_koppelingen


def test_damo_source_discovered_only_when_present(tmp_path):
    from waterlagen.datastore import DataStore
    from waterlagen.functioneel_landgebruik import FunctioneelLandgebruikSources

    store = DataStore(data_dir=tmp_path)
    assert FunctioneelLandgebruikSources.from_datastore(store).rwzi_gpkg is None
    path = store.waterketen_damo_dir / "waterketen_damo.gpkg"
    path.touch()
    assert FunctioneelLandgebruikSources.from_datastore(store).rwzi_gpkg == path


def test_rwzi_production_codes_and_excluded_bag_status(tmp_path):
    from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import prepare_bag

    top, damo, bag = [tmp_path / f"{name}.gpkg" for name in ["top", "damo", "bag"]]
    write_top(top)
    gpd.GeoDataFrame(
        {"typefunctioneelgebied": ["zuiveringsinstallatie"]},
        geometry=[box(0, 0, 100, 100)],
        crs="EPSG:28992",
    ).to_file(top, layer="top10nl_functioneel_gebied_vlak", driver="GPKG")
    gpd.GeoDataFrame(geometry=[Point(90, 90)], crs="EPSG:28992").to_file(
        damo, layer="rwzi", driver="GPKG"
    )
    gpd.GeoDataFrame(
        {
            "identificatie": ["in", "out", "excluded"],
            "status": ["Pand in gebruik", "Pand in gebruik", "Pand gesloopt"],
        },
        geometry=[box(1, 1, 3, 3), box(6, 1, 8, 3), box(11, 1, 13, 3)],
        crs="EPSG:28992",
    ).to_file(bag, layer="pand", driver="GPKG")
    gpd.GeoDataFrame(
        {
            "identificatie": ["v1", "v2", "v3"],
            "pand_identificatie": ["in", "out", "excluded"],
            "gebruiksdoel": ["kantoorfunctie"] * 3,
            "oppervlakte": [4] * 3,
        },
        geometry=[Point(2, 2), Point(7, 2), Point(12, 2)],
        crs="EPSG:28992",
    ).to_file(bag, layer="verblijfsobject", driver="GPKG")
    result = prepare_bag(
        bag,
        pand_layer="pand",
        verblijfsobject_layer="verblijfsobject",
        bounds=(0, 0, 15, 5),
        buitendijks_area=box(5, 0, 15, 5),
        include_details=True,
        special_sources=SpecialBuildingSources(top, rwzi_gpkg=damo),
    )
    assert result.identificatie.tolist() == ["in", "out"]
    assert result.code.tolist() == [36, 164]
    assert result.lgb_omschrijving.tolist() == ["RWZI (gebouw op RWZI-terrein)"] * 2
    assert result.basis_lgb_code_binnendijks.tolist() == [17, 17]


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
