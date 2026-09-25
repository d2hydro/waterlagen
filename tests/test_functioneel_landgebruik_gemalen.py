import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box
from test_functioneel_landgebruik_kassen_rwzi_drinkwater import buildings

from waterlagen.functioneel_landgebruik.gemalen import (
    classify_pumping_stations,
    link_pumping_stations,
)


def stations(capacities, points=None, ids=None):
    return classify_pumping_stations(
        gpd.GeoDataFrame(
            {
                "maximalecapaciteit": capacities,
                "globalid": ids or [f"g{i}" for i in range(len(capacities))],
            },
            geometry=points or [Point(5, 5)] * len(capacities),
            crs="EPSG:28992",
        )
    )


@pytest.mark.parametrize(
    "capacity,expected",
    [
        (None, None),
        ("unknown", None),
        (-1, None),
        (float("inf"), None),
        (9.9, None),
        (10, 38),
        (19.99, 38),
        (20, 39),
        (50, 40),
        (100, 41),
        (400, 42),
        (1000, 42),
        (1000.1, 43),
    ],
)
def test_six_capacity_boundaries(capacity, expected):
    result = stations([capacity]).iloc[0]
    if expected is None:
        assert pd.isna(result.lgb_code_binnendijks)
    else:
        assert result.lgb_code_binnendijks == expected
        assert result.lgb_code_buitendijks == expected + 128


def test_sum_distinct_gemalen_and_deduplicate_ids():
    panden = buildings([box(0, 0, 10, 10)])
    points = stations([20, 35, 20], ids=["{A}", "b", "a"])
    result = link_pumping_stations(panden, points)
    assert result.panden.iloc[0].gemaalcapaciteit_m3_min == 55
    assert result.panden.iloc[0].lgb_code_binnendijks == 40
    assert result.gemalen.geometrie_kaart.tolist() == ["BAG-pand"] * 3
    assert result.gemalen.pand_capaciteit_m3_min.tolist() == [55] * 3
    assert result.panden.geometry.equals(panden.geometry)


@pytest.mark.parametrize(
    "goals",
    [
        "woonfunctie",
        "industriefunctie,woonfunctie",
        "onderwijsfunctie",
        "kantoorfunctie",
        "industriefunctie,ontbreekt",
        "woonfunctie,ontbreekt",
        "onbekende bronwaarde",
        None,
        pd.NA,
    ],
)
def test_residential_or_unknown_function_never_gets_whole_gemaal_class(goals):
    panden = buildings([box(0, 0, 10, 10)])
    panden["alle_bag_gebruiksdoelen"] = goals
    # A chosen main function must not hide a residential VBO.
    panden["gekozen_pandfunctie"] = "industriefunctie"
    result = link_pumping_stations(panden, stations([50]))
    assert result.panden.iloc[0].lgb_code_binnendijks == 33
    assert result.gemalen.iloc[0].geometrie_kaart == "punt"
    assert "Pandfunctie" in result.gemalen.iloc[0].reden_ruimtelijke_koppeling


@pytest.mark.parametrize("goals", ["", "ontbreekt"])
def test_absent_bag_use_allows_summed_pump_capacity(goals):
    panden = buildings([box(0, 0, 10, 10)])
    panden["alle_bag_gebruiksdoelen"] = goals
    result = link_pumping_stations(panden, stations([20, 35]))
    assert result.panden.iloc[0].gemaalcapaciteit_m3_min == 55
    assert result.panden.iloc[0].lgb_code_binnendijks == 40
    assert result.gemalen.geometrie_kaart.tolist() == ["BAG-pand"] * 2
    assert "lege gebruiksdoelen" in result.panden.iloc[0].reden_klasse
    assert result.panden.geometry.equals(panden.geometry)


def test_missing_bag_use_column_is_not_evidence_of_absent_use():
    panden = buildings([box(0, 0, 10, 10)]).drop(columns="alle_bag_gebruiksdoelen")
    result = link_pumping_stations(panden, stations([50]))
    assert result.gemalen.iloc[0].geometrie_kaart == "punt"


def test_no_nearest_building_and_boundary_or_ambiguous_matches_stay_points():
    panden = buildings([box(0, 0, 10, 10), box(0, 0, 10, 10)])
    result = link_pumping_stations(
        panden, stations([50] * 3, [Point(5, 5), Point(10, 5), Point(11, 5)])
    )
    assert result.gemalen.aantal_bag_panden.tolist() == [2, 0, 0]
    assert result.gemalen.geometrie_kaart.tolist() == ["punt"] * 3
    assert result.panden.lgb_code_binnendijks.tolist() == [33, 33]


@pytest.mark.parametrize(
    "capacities,ids",
    [([20, None], ["a", "b"]), ([20, 30], ["a", "a"]), ([20, 30], ["", "b"])],
)
@pytest.mark.parametrize("goals", ["overige gebruiksfunctie", "", "ontbreekt"])
def test_incomplete_or_conflicting_total_does_not_override_bag(capacities, ids, goals):
    panden = buildings([box(0, 0, 10, 10)])
    panden["alle_bag_gebruiksdoelen"] = goals
    result = link_pumping_stations(panden, stations(capacities, ids=ids))
    assert result.panden.iloc[0].lgb_code_binnendijks == 33
    assert result.gemalen.geometrie_kaart.tolist() == ["punt"] * 2


def test_small_stations_are_classified_after_summing():
    result = link_pumping_stations(buildings([box(0, 0, 10, 10)]), stations([6, 6]))
    assert result.panden.iloc[0].lgb_code_binnendijks == 38
    assert result.panden.iloc[0].gemaalcapaciteit_m3_min == 12


def test_control_and_national_raster_use_same_pump_decisions(tmp_path):
    import runpy
    from pathlib import Path

    import rasterio

    from waterlagen import _geopandas as wgpd
    from waterlagen.datastore import DataStore
    from waterlagen.functioneel_landgebruik import (
        FunctioneelLandgebruikSources,
        bouw_functioneel_landgebruik,
    )
    from waterlagen.raster.config import RasterOutputConfig

    store = DataStore(data_dir=tmp_path)
    pump_path = store.source_data_dir / "hydamo" / "hydamo.gpkg"
    pump_path.parent.mkdir(parents=True, exist_ok=True)
    points = stations(
        [40, 30, 50, 20],
        [Point(2, 2), Point(4, 4), Point(13.5, 1.5), Point(24.5, 11.5)],
    )
    points[["maximalecapaciteit", "globalid", "geometry"]].to_file(
        pump_path, layer="gemaal", driver="GPKG"
    )
    sources = FunctioneelLandgebruikSources.from_datastore(store)
    panden = gpd.GeoDataFrame(
        {
            "identificatie": ["industrial", "residential"],
            "status": ["Pand in gebruik"] * 2,
        },
        geometry=[box(0, 0, 10, 10), box(12, 0, 22, 10)],
        crs="EPSG:28992",
    )
    panden.to_file(sources.bag_gpkg, layer="pand", driver="GPKG")
    gpd.GeoDataFrame(
        {
            "identificatie": ["v1", "v2"],
            "pand_identificatie": ["industrial", "residential"],
            "gebruiksdoel": ["industriefunctie", "woonfunctie"],
            "oppervlakte": [100, 100],
        },
        geometry=[Point(5, 5), Point(15, 5)],
        crs=panden.crs,
    ).to_file(sources.bag_gpkg, layer="verblijfsobject", driver="GPKG")
    for layer, field in [
        ("bgt_waterdeel", "naam"),
        ("bgt_wegdeel", "bgt-functie"),
        ("bgt_ondersteunendwegdeel", "bgt-functie"),
        ("bgt_begroeidterreindeel", "bgt-fysiekVoorkomen"),
        ("bgt_onbegroeidterreindeel", "naam"),
    ]:
        gpd.GeoDataFrame(
            {field: [], "bgt-status": [], "eindRegistratie": [], "objectEindTijd": []},
            geometry=[],
            crs=panden.crs,
        ).to_file(sources.bgt_gpkg, layer=layer, driver="GPKG")
    gpd.GeoDataFrame({"gewascode": []}, geometry=[], crs=panden.crs).to_file(
        sources.brp_gpkg, layer="brp_gewas", driver="GPKG"
    )
    for layer, field in [
        ("top10nl_gebouw_vlak", "typegebouw"),
        ("top10nl_functioneel_gebied_vlak", "typefunctioneelgebied"),
        ("top10nl_functioneel_gebied_multivlak", "typefunctioneelgebied"),
    ]:
        gpd.GeoDataFrame({field: []}, geometry=[], crs=panden.crs).to_file(
            sources.top10nl_gpkg, layer=layer, driver="GPKG"
        )
    gpd.GeoDataFrame(geometry=[box(-1, -1, 30, 20)], crs=panden.crs).to_file(
        sources.dijkringen_gpkg, layer="dijkring_v_2012", driver="GPKG"
    )
    script = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts/controle_bag_landgebruik.py")
    )
    control_path = script["main"](store, bounds=(0, 0, 25, 12), stap=6)
    control = wgpd.read_file(control_path, layer="bag_controle")
    control_points = wgpd.read_file(control_path, layer="gemalen_controle")
    assert control.lgb_code_binnendijks.tolist() == [40, 1]
    assert control_points.geometrie_kaart.tolist() == [
        "BAG-pand",
        "BAG-pand",
        "punt",
        "punt",
    ]
    assert control.iloc[0].gemaalcapaciteit_m3_min == 70
    output = bouw_functioneel_landgebruik(
        tmp_path / "result.tif",
        bounds=(0, 0, 25, 12),
        resolution_m=1,
        sources=sources,
        download_missing_sources=False,
        output_config=RasterOutputConfig(block_size=16, overview_factors=()),
    )
    with rasterio.open(output) as raster:
        values = raster.read(1)
        assert values[7, 5] == control.iloc[0].lgb_code_binnendijks
        assert values[7, 17] == control.iloc[1].lgb_code_binnendijks
        assert values[0, 24] == 39  # Unmatched point, one cell.
        assert values[10, 13] == 40  # Rejected residential match remains a point.
