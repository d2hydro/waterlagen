"""Check CSV edits through actual classification, not just the table reader."""

import csv
from pathlib import Path

import geopandas as gpd
import pytest
import rasterio
from shapely.geometry import MultiPolygon, box

from waterlagen.functioneel_landgebruik.bag_landgebruik import determine_bag_classes
from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import (
    prepare_bgt_layer,
    prepare_brp,
    prepare_functionele_gebieden,
    prepare_water,
    prepare_wegen,
)
from waterlagen.functioneel_landgebruik.landgebruik_berekenen import (
    FunctioneelLandgebruikSources,
    bouw_functioneel_landgebruik,
)
from waterlagen.functioneel_landgebruik.landgebruikstabel import (
    DEFAULT_MAPPING_CSV,
    load_landuse_table,
)
from waterlagen.raster.config import RasterOutputConfig


def _changed_csv(tmp_path, mapping_id, **changes):
    legacy_csv = Path(__file__).parent / "fixtures" / "landgebruik_legacy.csv"
    with legacy_csv.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    row = next(row for row in rows if mapping_id in row["Koppeling-ID"].splitlines())
    row.update(changes)
    path = tmp_path / "codes.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(reversed(rows))
    return path


def _data(values, field):
    return gpd.GeoDataFrame(
        {field: values},
        geometry=[box(i * 2, 0, i * 2 + 1, 1) for i in range(len(values))],
        crs="EPSG:28992",
    )


def _current(data):
    result = data.copy()
    result["bgt-status"] = "bestaand"
    result["eindRegistratie"] = None
    result["objectEindTijd"] = None
    return result


@pytest.mark.parametrize("source", ["BRP", "TOP10NL", "BGT"])
def test_source_crs_must_match_project(tmp_path, source):
    path = tmp_path / "wrong_crs.gpkg"
    if source == "BRP":
        data = _data([2014], "gewascode")
        layer = "brp_gewas"
        prepare = prepare_brp
    elif source == "TOP10NL":
        data = _data(["volkstuinen"], "typefunctioneelgebied")
        layer = "top10nl_functioneel_gebied_vlak"
        prepare = prepare_functionele_gebieden
    else:
        data = _current(_data(["water"], "naam"))
        layer = "bgt_waterdeel"
        prepare = prepare_water
    data.set_crs(4326, allow_override=True).to_file(path, layer=layer, driver="GPKG")
    with pytest.raises(ValueError, match="CRS.*verschilt"):
        prepare(path, layer=layer, bounds=(-1, -1, 2, 2), dike_area=box(-1, -1, 2, 2))


def test_csv_codes_not_offsets_or_row_order_determine_bag_class(tmp_path):
    path = _changed_csv(
        tmp_path,
        "BAG-002",
        Binnen="110",
        Buiten="240",
        **{"Landgebruik volgens notitie": "Aangepaste woningklasse"},
    )
    panden = _data(["woonfunctie"], "gekozen_pandfunctie")
    panden["bron_aantal_vbo"] = 1
    panden["berekend_aantal_bouwlagen"] = 2
    panden["som_vbo_oppervlakte_m2"] = 2
    panden["functiekeuze_status"] = "gekozen"
    result = determine_bag_classes(panden, table=load_landuse_table(path)).iloc[0]
    assert result["lgb_code_binnendijks"] == 110
    assert result["lgb_code_buitendijks"] == 240
    assert result["lgb_omschrijving"] == "Aangepaste woningklasse"
    assert result["lgb_koppeling_id"] == "BAG-002"


@pytest.mark.parametrize(
    "mapping_id,column,value,expected",
    [
        ("BAG-002", "Bronwaarde", "winkelfunctie", "woonfunctie"),
        ("BAG-002", "Bronwaarde", "woonfunctie\nwinkelfunctie", "woonfunctie"),
        ("BAG-031", "Bronwaarde", "kantoorfunctie", "woonfunctie"),
        ("BAG-032", "Bronwaarde", "woonfunctie", "overige gebruiksfunctie"),
        ("BAG-033", "Bronwaarde", "woonfunctie", "overige gebruiksfunctie"),
        ("BAG-002", "Bron", "BGT", "bron BAG"),
        ("BAG-034", "Bron", "BGT", "bron BAG"),
    ],
)
def test_bag_rejects_csv_ids_reassigned_to_another_function_or_source(
    tmp_path, mapping_id, column, value, expected
):
    path = _changed_csv(tmp_path, mapping_id, **{column: value})
    panden = _data(["woonfunctie"], "gekozen_pandfunctie")
    panden["bron_aantal_vbo"] = 1
    panden["berekend_aantal_bouwlagen"] = 2
    panden["som_vbo_oppervlakte_m2"] = 100
    panden["functiekeuze_status"] = "gekozen"

    with pytest.raises(ValueError) as error:
        determine_bag_classes(panden, table=load_landuse_table(path))

    message = str(error.value)
    assert str(path) in message
    assert mapping_id in message
    assert expected in message


@pytest.mark.parametrize("value", ["0", "256", "abc", "178\nNog kiezen", ""])
def test_invalid_codes_stop_processing(tmp_path, value):
    path = _changed_csv(tmp_path, "BAG-002", Buiten=value)
    with pytest.raises(ValueError, match="Buiten"):
        load_landuse_table(path)


def test_duplicate_ids_and_conflicting_codes_are_rejected(tmp_path):
    path = _changed_csv(tmp_path, "BAG-002", **{"Koppeling-ID": "BAG-001"})
    with pytest.raises(ValueError, match="Koppeling-ID"):
        load_landuse_table(path)
    path = _changed_csv(tmp_path, "BGT-033", Binnen="1")
    with pytest.raises(ValueError, match="verschillende landgebruiksklassen"):
        load_landuse_table(path)


@pytest.mark.parametrize("outside", [False, True])
def test_brp_exact_codes_grass_exception_and_explicit_fallback(tmp_path, outside):
    path = tmp_path / "brp.gpkg"
    # Grass, green manure, potatoes, other crops, nature, ditch, future code, invalid.
    data = _data([265, 266, 426, 2014, 174, 331, 343, 99999, None], "gewascode")
    data.to_file(path, layer="brp_gewas", driver="GPKG")
    result = prepare_brp(
        path,
        layer="brp_gewas",
        bounds=(-1, -1, 30, 2),
        dike_area=box(100, 100, 101, 101) if outside else box(-1, -1, 30, 2),
    )
    expected = (
        [182, 182, 178, 180, 181, 182, 182, 181]
        if outside
        else [50, 50, 50, 52, 53, 54, 54, 53]
    )
    assert result["code"].tolist() == expected


@pytest.mark.parametrize("layer_suffix", ["vlak", "multivlak"])
@pytest.mark.parametrize("outside", [False, True])
def test_top10_matches_whole_values_not_fragments(tmp_path, layer_suffix, outside):
    path = tmp_path / "top10.gpkg"
    layer = f"top10nl_functioneel_gebied_{layer_suffix}"
    data = _data(
        [
            "zonnepark",
            "park",
            "dierentuin, safaripark",
            "volkstuinen",
            "sportterrein, sportcomplex",
        ],
        "typefunctioneelgebied",
    )
    if layer_suffix == "multivlak":
        data.geometry = [
            MultiPolygon([geometry, box(i * 2, 3, i * 2 + 1, 4)])
            for i, geometry in enumerate(data.geometry)
        ]
    data.to_file(path, layer=layer, driver="GPKG")
    result = prepare_functionele_gebieden(
        path,
        layer=layer,
        bounds=(-1, -1, 30, 5),
        dike_area=box(100, 100, 101, 101) if outside else box(-1, -1, 30, 5),
    )
    assert result["code"].tolist() == [205 if outside else 77] * 3
    assert result.geometry.iloc[0].bounds[0] == 4
    assert result.geometry.iloc[0].equals(data.geometry.iloc[2])


def test_bgt_road_values_and_water_follow_csv(tmp_path):
    path = tmp_path / "bgt.gpkg"
    _current(
        _data(
            [
                "baan voor vliegverkeer",
                "overweg",
                "OV-baan",
                "inrit",
                "ruiterpad",
                "voetpad",
                "onbekend",
            ],
            "bgt-functie",
        )
    ).to_file(path, layer="bgt_wegdeel", driver="GPKG")
    _current(_data(["water"], "naam")).to_file(
        path, layer="bgt_waterdeel", driver="GPKG"
    )
    kwargs = {"bounds": (-1, -1, 30, 2), "dike_area": box(100, 100, 101, 101)}
    assert prepare_wegen(path, layer="bgt_wegdeel", **kwargs)["code"].tolist() == [
        198,
        199,
        202,
        203,
        206,
        203,
    ]
    assert prepare_water(path, layer="bgt_waterdeel", **kwargs)["code"].tolist() == [
        228
    ]
    csv_path = _changed_csv(tmp_path, "BGT-033", Buiten="245")
    assert prepare_water(
        path, layer="bgt_waterdeel", table=load_landuse_table(csv_path), **kwargs
    )["code"].tolist() == [245]


def test_current_terrain_replaces_ended_road(tmp_path):
    path = tmp_path / "bgt.gpkg"
    road = _current(_data(["voetpad"], "bgt-functie"))
    road["objectEindTijd"] = "2026-05-11"
    road.to_file(path, layer="bgt_wegdeel", driver="GPKG")
    _current(_data(["gemengd bos"], "bgt-fysiekVoorkomen")).to_file(
        path, layer="bgt_begroeidterreindeel", driver="GPKG"
    )
    kwargs = {"bounds": (-1, -1, 2, 2), "dike_area": box(-1, -1, 2, 2)}
    assert prepare_wegen(path, layer="bgt_wegdeel", **kwargs).empty
    terrain = prepare_bgt_layer(
        path,
        layer="bgt_begroeidterreindeel",
        mapping_layer="bgt_begroeidterreindeel",
        **kwargs,
    )
    assert terrain["code"].tolist() == [78]


def test_full_build_uses_csv_and_water_wins_over_building(tmp_path):
    sources = FunctioneelLandgebruikSources(
        bgt_gpkg=tmp_path / "bgt.gpkg",
        bag_gpkg=tmp_path / "bag.gpkg",
        brp_gpkg=tmp_path / "brp.gpkg",
        top10nl_gpkg=tmp_path / "top10.gpkg",
        dijkringen_gpkg=tmp_path / "dikes.gpkg",
    )
    # All sources overlap; a custom water code must win in the produced raster.
    for layer, field, value in [
        ("bgt_waterdeel", "naam", "water"),
        ("bgt_wegdeel", "bgt-functie", "voetpad"),
        ("bgt_ondersteunendwegdeel", "bgt-functie", "berm"),
        ("bgt_begroeidterreindeel", "bgt-fysiekVoorkomen", "gemengd bos"),
        ("bgt_onbegroeidterreindeel", "naam", "erf"),
    ]:
        _current(_data([value], field)).to_file(
            sources.bgt_gpkg, layer=layer, driver="GPKG"
        )
    pand = _data(["p1"], "identificatie")
    pand["status"] = "Pand in gebruik"
    pand.to_file(sources.bag_gpkg, layer="pand", driver="GPKG")
    vbo = _data(["v1"], "identificatie")
    vbo["pand_identificatie"] = "p1"
    vbo["gebruiksdoel"] = "woonfunctie"
    vbo["oppervlakte"] = 1
    vbo.geometry = vbo.geometry.representative_point()
    vbo.to_file(sources.bag_gpkg, layer="verblijfsobject", driver="GPKG")
    _data([2014], "gewascode").to_file(
        sources.brp_gpkg, layer="brp_gewas", driver="GPKG"
    )
    _data(["volkstuinen"], "typefunctioneelgebied").to_file(
        sources.top10nl_gpkg, layer="top10nl_functioneel_gebied_vlak", driver="GPKG"
    )
    gpd.GeoDataFrame(
        {"typefunctioneelgebied": ["volkstuinen", "sportterrein, sportcomplex"]},
        geometry=[
            MultiPolygon([box(0, 0, 1, 1), box(2, 0, 3, 1)]),
            MultiPolygon([box(4, 0, 5, 1), box(4, 2, 5, 3)]),
        ],
        crs="EPSG:28992",
    ).to_file(
        sources.top10nl_gpkg,
        layer="top10nl_functioneel_gebied_multivlak",
        driver="GPKG",
    )
    _data(["kas, warenhuis"], "typegebouw").to_file(
        sources.top10nl_gpkg, layer="top10nl_gebouw_vlak", driver="GPKG"
    )
    gpd.GeoDataFrame(geometry=[box(-1, -1, 3.5, 4)], crs="EPSG:28992").to_file(
        sources.dijkringen_gpkg, layer="dijkring_v_2012", driver="GPKG"
    )
    csv_path = _changed_csv(tmp_path, "BGT-033", Binnen="110")
    output = bouw_functioneel_landgebruik(
        tmp_path / "result.tif",
        bounds=(0, 0, 6, 4),
        resolution_m=1,
        sources=sources,
        download_missing_sources=False,
        mapping_csv=csv_path,
        output_config=RasterOutputConfig(block_size=16, overview_factors=()),
    )
    with rasterio.open(output) as raster:
        values = raster.read(1)
        colors = raster.colormap(1)
        assert values[3, 0] == 110  # Water still wins over both TOP10NL layers.
        assert values[3, 2] == 77  # Separate part of the inside multivlak.
        assert values[3, 4] == 205
        assert values[1, 4] == 205  # Both parts of the outside multivlak.
        assert raster.colormap(1)[110][:3] == (0, 130, 255)
        assert raster.nodata == 0
    style = output.with_suffix(".qml").read_bytes()
    with DEFAULT_MAPPING_CSV.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    water = next(row for row in rows if row["Bronlaag"] == "bgt_waterdeel")
    water["LGB-code_binnendijks"] = "110"
    for reverse in (False, True):
        if reverse:
            rows.reverse()
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=";")
            writer.writeheader()
            writer.writerows(rows)
        custom_output = bouw_functioneel_landgebruik(
            tmp_path / f"custom_{reverse}.tif",
            bounds=(0, 0, 6, 4),
            resolution_m=1,
            sources=sources,
            download_missing_sources=False,
            mapping_csv=csv_path,
            output_config=RasterOutputConfig(block_size=16, overview_factors=()),
        )
        with rasterio.open(custom_output) as raster:
            assert (raster.read(1) == values).all()
            assert raster.colormap(1) == colors
        assert custom_output.with_suffix(".qml").read_bytes() == style
