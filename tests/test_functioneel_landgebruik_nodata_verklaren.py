"""Controle-uitvoer beschrijft echte beslissingen, zonder de kaart te veranderen."""

import os

import geopandas as gpd
import numpy as np
import pyogrio
import pytest
import rasterio
from shapely.geometry import Point, box

from waterlagen.functioneel_landgebruik import (
    FunctioneelLandgebruikSources,
    bouw_functioneel_landgebruik,
)
from waterlagen.functioneel_landgebruik.nodata_verklaren import (
    LanduseDiagnostics,
    _nodata_polygons,
    _unused_bgt,
    merge_diagnostics,
    validate_diagnostics,
)


def test_unused_bgt_only_current_polygons_and_concrete_reason(tmp_path):
    path = tmp_path / "extra.gpkg"
    _write(
        path,
        "bgt_ondersteunendwaterdeel",
        [box(i, 0, i + 1, 1) for i in range(4)],
        **{
            "bgt-type": ["oever, slootkant"] * 4,
            "bgt-status": ["bestaand", "bestaand", "bestaand", "plan"],
            "eindRegistratie": [None, "2020-01-01", None, None],
            "objectEindTijd": [None, None, "2020-01-01", None],
        },
    )
    result = _unused_bgt(path, (0, 0, 4, 1), "EPSG:28992")
    assert len(result) == 1
    assert result.iloc[0].bron == "BGT"
    assert result.iloc[0].reden == "Oever/slootkant: geen landgebruikscode."


def test_unused_bgt_before_top10_and_history_but_not_bag():
    records = gpd.GeoDataFrame(
        {
            "bron": ["BGT", "BAG"],
            "reden": ["Historisch", "Functiekeuze open"],
            "direct": [False, True],
        },
        geometry=[box(0, 0, 3, 1), box(0, 0, 1, 1)],
        crs=28992,
    )
    extra = gpd.GeoDataFrame(
        {
            "bron": ["BGT"],
            "reden": ["Oever/slootkant: geen landgebruikscode."],
        },
        geometry=[box(0, 0, 3, 1)],
        crs=28992,
    )
    terrain = gpd.GeoDataFrame(
        {"reden": ["Grasland"]}, geometry=[box(0, 0, 4, 1)], crs=28992
    )
    result = _nodata_polygons(
        np.ones((1, 4), dtype=bool),
        records,
        rasterio.transform.from_origin(0, 1, 1, 1),
        "EPSG:28992",
        terrains=terrain,
        unused_bgt=extra,
    )
    assert "Historisch" not in result.reden.tolist()
    assert set(result.bron) == {"BAG", "BGT", "TOP10NL"}
    assert result.loc[result.bron.eq("BAG"), "reden"].tolist() == ["Functiekeuze open"]


from waterlagen.raster.config import RasterOutputConfig


def _write(path, layer, geometry, **columns):
    gpd.GeoDataFrame(columns, geometry=geometry, crs="EPSG:28992").to_file(
        path, layer=layer, driver="GPKG"
    )


@pytest.fixture
def sources(tmp_path):
    source = FunctioneelLandgebruikSources(
        bgt_gpkg=tmp_path / "bgt.gpkg",
        bag_gpkg=tmp_path / "bag.gpkg",
        brp_gpkg=tmp_path / "brp.gpkg",
        top10nl_gpkg=tmp_path / "top10.gpkg",
        dijkringen_gpkg=tmp_path / "dikes.gpkg",
        gemalen_gpkg=tmp_path / "gemalen.gpkg",
    )
    for layer, geometries, field, values, end in [
        (
            "bgt_waterdeel",
            [box(2, 2, 4, 4), box(2, 0, 4, 2)],
            "naam",
            ["water", "oud water"],
            [None, "2025-01-01"],
        ),
        ("bgt_wegdeel", [box(2, 0, 4, 2)], "bgt-functie", ["voetpad"], ["2025-01-01"]),
        ("bgt_ondersteunendwegdeel", [], "bgt-functie", [], []),
        (
            "bgt_begroeidterreindeel",
            [box(0, 2, 2, 4), box(4, 0, 6, 2)],
            "bgt-fysiekVoorkomen",
            ["gemengd bos", "bouwland"],
            [None, None],
        ),
        ("bgt_onbegroeidterreindeel", [], "naam", [], []),
    ]:
        _write(
            source.bgt_gpkg,
            layer,
            geometries,
            **{
                field: values,
                "bgt-status": ["bestaand"] * len(values),
                "eindRegistratie": end,
                "objectEindTijd": end
                if layer == "bgt_wegdeel"
                else [None] * len(values),
            },
        )
    ids = ["open", "water", "gesloopt", "kas", "oppervlak", "pomphuis"]
    _write(
        source.bag_gpkg,
        "pand",
        [box(x, 2, x + 2, 4) for x in range(0, 12, 2)],
        identificatie=ids,
        status=[
            "Pand in gebruik",
            "Pand in gebruik",
            "Pand gesloopt",
            "Pand in gebruik",
            "Pand in gebruik",
            "Pand in gebruik",
        ],
    )
    _write(
        source.bag_gpkg,
        "verblijfsobject",
        [Point(x + 1, 3) for x in range(0, 10, 2)],
        identificatie=[f"v{i}" for i in range(5)],
        pand_identificatie=ids[:5],
        gebruiksdoel=["onderwijsfunctie,sportfunctie"] * 4 + ["kantoorfunctie"],
        oppervlakte=[4.0, 4.0, 4.0, 4.0, np.nan],
    )
    _write(
        source.top10nl_gpkg,
        "top10nl_gebouw_vlak",
        [box(6, 2, 8, 4)],
        typegebouw=["kas, warenhuis"],
    )
    _write(
        source.top10nl_gpkg,
        "top10nl_functioneel_gebied_vlak",
        [box(0, 0, 2, 2)],
        typefunctioneelgebied=["zonnepark"],
    )
    _write(
        source.top10nl_gpkg,
        "top10nl_functioneel_gebied_multivlak",
        [box(2, 0, 4, 2)],
        typefunctioneelgebied=["natuurgebied"],
    )
    _write(
        source.brp_gpkg,
        "brp_gewas",
        [box(0, 0, 2, 2), box(4, 0, 6, 2)],
        gewascode=[2014.0, np.nan],
    )
    _write(source.dijkringen_gpkg, "dijkring_v_2012", [box(-1, -1, 20, 20)])
    _write(
        source.gemalen_gpkg,
        "gemaal",
        [Point(5, 1), Point(10.5, 3), Point(11.5, 3)],
        globalid=["ontbreekt", "gemaal1", "gemaal2"],
        maximalecapaciteit=[np.nan, 6.0, 6.0],
    )
    return source


def _build(tmp_path, sources, *, control=True, name="landgebruik"):
    raster = tmp_path / f"{name}.tif"
    control_path = tmp_path / f"{name}.gpkg"
    bouw_functioneel_landgebruik(
        raster,
        bounds=(0, 0, 12, 4),
        resolution_m=1,
        sources=sources,
        download_missing_sources=False,
        diagnostics_path=control_path if control else None,
        output_config=RasterOutputConfig(block_size=16, overview_factors=()),
    )
    return raster, control_path


def test_control_only_contains_empty_cells_and_reason(tmp_path, sources):
    raster, control = _build(tmp_path, sources)
    without, _ = _build(tmp_path, sources, control=False, name="zonder_controle")
    polygons = gpd.read_file(control, layer="nodata")
    assert pyogrio.list_layers(control)[:, 0].tolist() == ["nodata"]
    assert set(polygons.columns) == {"bron", "reden", "geometry"}
    with rasterio.open(raster) as a, rasterio.open(without) as b:
        np.testing.assert_array_equal(a.read(1), b.read(1))
        mask = rasterio.features.rasterize(
            [(geometry, 1) for geometry in polygons.geometry],
            out_shape=a.shape,
            transform=a.transform,
            fill=0,
            dtype="uint8",
        )
        np.testing.assert_array_equal(mask, a.read(1) == 0)
        assert polygons.geometry.area.sum() == int((a.read(1) == 0).sum())
    assert polygons.geometry.union_all().area == polygons.geometry.area.sum()

    def reasons_at(x, y):
        selected = polygons.loc[polygons.geometry.covers(Point(x, y))]
        return " ".join(selected.reden)

    assert "onderwijsfunctie, sportfunctie: 4 m² niet uitgesplitst" in reasons_at(
        0.5, 3.5
    )
    assert "BGT" not in reasons_at(0.5, 3.5)  # De directe BAG-oorzaak gaat voor.
    assert "oppervlakte" in reasons_at(8.5, 3.5).lower()
    assert "BGT" in reasons_at(2.5, 0.5)
    assert "TOP10NL" in reasons_at(2.5, 0.5)  # Beide aanwijzingen blijven zichtbaar.
    assert "BRP" in reasons_at(5.5, 0.5)
    assert "HyDAMO" in reasons_at(5.5, 0.5)
    for x, y in [(0.5, 0.5), (2.5, 3.5), (6.5, 3.5), (10.5, 3.5)]:
        assert not reasons_at(x, y)  # Ingevuld door BRP, water, kas of pomphuis.
    validate_diagnostics(control, raster)


def test_reuse_rejects_missing_or_stale_control(tmp_path, sources):
    raster, control = _build(tmp_path, sources)
    os.utime(
        raster, ns=(raster.stat().st_atime_ns, raster.stat().st_mtime_ns + 10_000_000)
    )
    with pytest.raises(ValueError, match="huidige raster"):
        bouw_functioneel_landgebruik(
            raster, bounds=(0, 0, 12, 4), overwrite=False, diagnostics_path=control
        )
    control.unlink()
    with pytest.raises(FileNotFoundError, match="opnieuw"):
        bouw_functioneel_landgebruik(
            raster, bounds=(0, 0, 12, 4), overwrite=False, diagnostics_path=control
        )


def test_merge_removes_intermediate_controls(tmp_path, sources):
    raster, first = _build(tmp_path, sources, name="eerste")
    _, second = _build(tmp_path, sources, name="tweede")
    expected = gpd.read_file(first, layer="nodata")
    merged = merge_diagnostics(
        [first, second], tmp_path / "gezamenlijk.gpkg", remove_sources=True
    )
    assert not first.exists()
    assert not second.exists()
    records = gpd.read_file(merged, layer="nodata")
    assert set(records.columns) == {"bron", "reden", "geometry"}
    assert len(records) == 2 * len(expected)
    assert pyogrio.list_layers(merged)[:, 0].tolist() == ["nodata"]
    validate_diagnostics(merged, raster)


@pytest.mark.parametrize("value", [0, 100])
def test_uncovered_cells_and_completely_filled_raster(tmp_path, value):
    raster = tmp_path / "leeg.tif"
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="uint8",
        crs="EPSG:28992",
        transform=rasterio.transform.from_origin(0, 2, 1, 1),
        nodata=0,
    ) as dst:
        dst.write(np.full((2, 2), value, dtype="uint8"), 1)
    control = LanduseDiagnostics().write(tmp_path / "leeg.gpkg", raster_path=raster)
    assert pyogrio.list_layers(control)[:, 0].tolist() == ["nodata"]
    polygons = gpd.read_file(control, layer="nodata")
    assert set(polygons.columns) == {"bron", "reden", "geometry"}
    if value == 0:
        assert len(polygons) == 1
        assert polygons.iloc[0].reden == "Geen bron vult deze plek."
        assert polygons.iloc[0].geometry.area == 4
    else:
        assert polygons.empty
    validate_diagnostics(control, raster)


def test_unused_top10_terrain_explains_only_unknown_nodata(tmp_path):
    raster = tmp_path / "landgebruik.tif"
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        width=4,
        height=1,
        count=1,
        dtype="uint8",
        crs="EPSG:28992",
        transform=rasterio.transform.from_origin(0, 1, 1, 1),
        nodata=0,
    ) as dst:
        dst.write(np.array([[0, 0, 100, 0]], dtype="uint8"), 1)
    top10 = tmp_path / "top10.gpkg"
    gpd.GeoDataFrame(
        {"typelandgebruik": ["grasland"]},
        geometry=[box(0, 0, 3, 1)],
        crs="EPSG:28992",
    ).to_file(top10, layer="top10nl_terrein_vlak", driver="GPKG")
    diagnostics = LanduseDiagnostics()
    diagnostics.add(
        gpd.GeoDataFrame(geometry=[box(0.1, 0.1, 0.9, 0.9)], crs="EPSG:28992"),
        source="BAG",
        source_path=tmp_path / "bag.gpkg",
        layer="pand",
        stage="Gebouwklasse",
        reason="Functiekeuze ontbreekt.",
        writes_nodata=True,
    )
    output = diagnostics.write(
        tmp_path / "controle.gpkg", raster_path=raster, top10nl_gpkg=top10
    )
    data = gpd.read_file(output, layer="nodata")
    assert data.area.sum() == 3
    first = data.loc[data.geometry.covers(Point(0.5, 0.5))].iloc[0]
    assert first.bron == "BAG"
    assert first.reden == "Functiekeuze ontbreekt."
    second = data.loc[data.geometry.covers(Point(1.5, 0.5))].iloc[0]
    assert second.bron == "TOP10NL"
    assert second.reden == "grasland: terreinlaag niet gebruikt."
    assert not data.geometry.covers(Point(2.5, 0.5)).any()
    last = data.loc[data.geometry.covers(Point(3.5, 0.5))].iloc[0]
    assert last.bron == "Niet vastgesteld"
    with rasterio.open(raster) as src:
        np.testing.assert_array_equal(src.read(1), [[0, 0, 100, 0]])


def test_failed_merge_keeps_previous_output(tmp_path):
    target = tmp_path / "controle.gpkg"
    target.write_bytes(b"bestaande uitvoer")
    with pytest.raises(pyogrio.errors.DataSourceError):
        merge_diagnostics([tmp_path / "ontbreekt.gpkg"], target)
    assert target.read_bytes() == b"bestaande uitvoer"


def test_nodata_on_both_sides_of_processing_boundary(tmp_path):
    raster = tmp_path / "twee_blokken.tif"
    values = np.zeros((2, 2050), dtype="uint8")
    values[:, 2047] = 100
    transform = rasterio.transform.from_origin(0, 2, 1, 1)
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        width=2050,
        height=2,
        count=1,
        dtype="uint8",
        crs="EPSG:28992",
        transform=transform,
        nodata=0,
    ) as dst:
        dst.write(values, 1)
    diagnostics = LanduseDiagnostics()
    diagnostics.add(
        gpd.GeoDataFrame(geometry=[box(2046, 0, 2050, 2)], crs="EPSG:28992"),
        source="BAG",
        source_path=tmp_path / "bag.gpkg",
        layer="pand",
        stage="Gebouwklasse",
        reason="Keuze nog open.",
        writes_nodata=True,
    )
    path = diagnostics.write(tmp_path / "controle.gpkg", raster_path=raster)
    data = gpd.read_file(path, layer="nodata")
    actual = rasterio.features.rasterize(
        [(geometry, 1) for geometry in data.geometry],
        out_shape=values.shape,
        transform=transform,
        fill=0,
        dtype="uint8",
    )
    np.testing.assert_array_equal(actual, values == 0)
    assert data.area.sum() == int((values == 0).sum())
    for point in [Point(2046.5, 0.5), Point(2048.5, 0.5)]:
        assert data.loc[data.geometry.covers(point)].iloc[0].reden == "Keuze nog open."


def test_oever_verbergt_alleen_overlappend_functioneelgebied():
    extra = gpd.GeoDataFrame(
        {
            "bron": ["BGT", "BGT"],
            "reden": [
                "Oever/slootkant: geen landgebruikscode.",
                "bgt_functioneelgebied: niet-bgt; laag niet verwerkt.",
            ],
        },
        geometry=[box(0, 0, 1, 1), box(0, 0, 2, 1)],
        crs=28992,
    )
    records = gpd.GeoDataFrame(
        {"bron": [], "reden": [], "direct": []},
        geometry=[],
        crs=28992,
    )
    result = _nodata_polygons(
        np.ones((1, 2), dtype=bool),
        records,
        rasterio.transform.from_origin(0, 1, 1, 1),
        "EPSG:28992",
        unused_bgt=extra,
    )
    oever = result.loc[result.geometry.covers(Point(0.5, 0.5))].iloc[0]
    assert oever.bron == "BGT"
    assert oever.reden == "Oever/slootkant: geen landgebruikscode."
    gebied = result.loc[result.geometry.covers(Point(1.5, 0.5))].iloc[0]
    assert gebied.reden == "bgt_functioneelgebied: niet-bgt; laag niet verwerkt."
    assert result.area.sum() == 2
