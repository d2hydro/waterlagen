"""Authority replacement and burn context use real small GeoPackages."""

import geopandas as gpd
import numpy as np
import pytest
import rasterio
import pyogrio
from shapely.geometry import LineString, Point, box

from waterlagen import _geopandas as wgpd
from waterlagen.afwateringseenheden import (
    Brandlaag,
    BrandlagenConfig,
    prepare_watersysteem,
    read_watersysteem_sources,
    write_watersysteem,
    calculate_subcatchments,
)
from waterlagen.afwateringseenheden.raster import prepare_watersysteem_rasters
from waterlagen.afwateringseenheden.sources import _source_ids


def test_compact_ids_survive_relocation_reindexing_and_selection(sources):
    from shutil import copyfile

    selected = read_watersysteem_sources(
        *sources, spatial_selection=box(-5, -5, 100, 100)
    )
    relocated_paths = []
    for path in sources:
        relocated = path.with_name(f"relocated_{path.name}")
        copyfile(path, relocated)
        relocated_paths.append(relocated)
    relocated = read_watersysteem_sources(
        *relocated_paths, spatial_selection=box(-5, -5, 100, 100)
    )
    assert selected.primary.bron_id.tolist() == relocated.primary.bron_id.tolist()
    assert selected.points.bron_id.is_unique
    before = prepare_watersysteem(selected.targets, selected.points)
    after = prepare_watersysteem(relocated.targets, relocated.points)
    assert before.hydroobject_segmenten.segment_key.tolist() == (
        after.hydroobject_segmenten.segment_key.tolist()
    )
    original = selected.primary.copy()
    original["bron_id"] = original.oorspronkelijk_bron_id
    original["bron_fid"] += 1000
    assert _source_ids(original).bron_id.tolist() == selected.primary.bron_id.tolist()
    assert (
        _source_ids(original.iloc[:1]).bron_id.iloc[0]
        == selected.primary.bron_id.iloc[0]
    )


def test_compact_ids_distinguish_parts_and_preserve_original_identity():
    features = gpd.GeoDataFrame(
        {
            "nen3610id": ["NL.WBHCODE.38.Hydroobject.6984"] * 2,
            "bronlaag": ["hydroobject"] * 2,
            "bron_fid": [7, 7],
            "globalid": ["shared", "shared"],
            "bron_id": ["shared:0001", "shared:0002"],
        },
        geometry=[LineString([(0, 0), (1, 0)]), LineString([(1, 0), (2, 0)])],
        crs=28992,
    )
    result = _source_ids(features)
    assert result.bron_id.is_unique
    assert result.oorspronkelijk_bron_id.tolist() == features.bron_id.tolist()
    assert result.bron_id.iloc[0] == "hydroobject:38.Hydroobject.6984:deel0001"
    duplicate = features.copy()
    duplicate["bron_id"] = "shared"
    with pytest.raises(ValueError, match="Duplicate source identifiers"):
        _source_ids(duplicate)


def test_compact_ids_do_not_misinterpret_original_id_as_part():
    features = gpd.GeoDataFrame(
        {
            "nen3610id": ["NL.WBHCODE.38.Hydroobject.6984"],
            "bronlaag": ["hydroobject"],
            "bron_fid": [7],
            "globalid": ["original:1234"],
            "bron_id": ["original:1234"],
        },
        geometry=[LineString([(0, 0), (1, 0)])],
        crs=28992,
    )
    assert _source_ids(features).bron_id.iloc[0] == "hydroobject:38.Hydroobject.6984"


def write_culverts(path, codes, geometries=None):
    gpd.GeoDataFrame(
        {
            "nen3610id": [f"NL.WBHCODE.{code}.{i}" for i, code in enumerate(codes)],
            "globalid": [str(i) for i in range(len(codes))],
        },
        geometry=geometries
        if geometries is not None
        else [LineString([(2, 0), (8, 0)])] * len(codes),
        crs=28992,
    ).to_file(path, layer="duikersifonhevel")


@pytest.mark.parametrize("others", [False, True])
@pytest.mark.parametrize("rws_layer", [False, True])
def test_culvert_sources_independent_of_targets_and_own_replacement(
    tmp_path, sources, others, rws_layer
):
    write_culverts(sources[0], ["30", "38", "80"])
    if rws_layer:
        write_culverts(sources[1], ["80"])
    selected = read_watersysteem_sources(
        *sources,
        spatial_selection=box(-1, -1, 100, 100),
        waterbeheercode="30",
        overige_waterschappen=others,
    )
    assert selected.rws_culverts_present is rws_layer
    assert selected.culverts.waterbeheercode.tolist() == (
        ["30", "38", "80"] if rws_layer else ["30", "38"]
    )
    assert selected.culverts.bron_id.is_unique
    assert selected.culverts.bron_fid.tolist() == ([1, 2, 1] if rws_layer else [1, 2])
    own = write_source(
        tmp_path / "own.gpkg", ["30"], ["primair"], [LineString([(0, 0), (10, 0)])]
    )
    replaced = read_watersysteem_sources(
        *sources,
        spatial_selection=box(-1, -1, 100, 100),
        waterbeheercode="30",
        overige_waterschappen=others,
        eigen_hydamo=own,
    )
    assert not replaced.culverts.waterbeheercode.eq("30").any()
    write_culverts(own, ["30"])
    replaced = read_watersysteem_sources(
        *sources,
        spatial_selection=box(-1, -1, 100, 100),
        waterbeheercode="30",
        overige_waterschappen=others,
        eigen_hydamo=own,
    )
    assert replaced.culverts.loc[
        replaced.culverts.waterbeheercode.eq("30")
    ].bronbestand.tolist() == [str(own)]


def test_required_culvert_layers_and_invalid_identifiers_outside_selection(
    tmp_path, sources
):
    own = write_source(
        tmp_path / "own.gpkg", ["30"], ["primair"], [LineString([(0, 0), (10, 0)])]
    )
    write_culverts(own, ["38"], [LineString([(1000, 1000), (1010, 1000)])])
    with pytest.raises(ValueError, match="nen3610id"):
        read_watersysteem_sources(
            *sources,
            spatial_selection=box(-1, -1, 100, 100),
            waterbeheercode="30",
            eigen_hydamo=own,
        )
    from osgeo import ogr

    dataset = ogr.Open(str(own), 1)
    dataset.DeleteLayer("duikersifonhevel")
    dataset = None
    with pytest.raises(ValueError, match="duikersifonhevel"):
        read_watersysteem_sources(
            *sources,
            spatial_selection=box(-1, -1, 100, 100),
            waterbeheercode="30",
            eigen_hydamo=own,
        )
    dataset = ogr.Open(str(sources[0]), 1)
    dataset.DeleteLayer("duikersifonhevel")
    dataset = None
    with pytest.raises(pyogrio.errors.DataLayerError, match="duikersifonhevel"):
        read_watersysteem_sources(*sources, spatial_selection=box(-1, -1, 100, 100))


def test_optional_rws_culverts_validated_and_presence_changes_signature(sources):
    selection = box(-1, -1, 100, 100)
    before = read_watersysteem_sources(*sources, spatial_selection=selection)
    write_culverts(sources[1], [])
    after = read_watersysteem_sources(*sources, spatial_selection=selection)
    assert before.culverts.empty and after.culverts.empty
    first = prepare_watersysteem(
        before.targets,
        before.points,
        hydroobject_primair=before.primary,
        duikersifonhevel=before.culverts,
    )
    second = prepare_watersysteem(
        after.targets,
        after.points,
        hydroobject_primair=after.primary,
        duikersifonhevel=after.culverts,
    )
    assert first.duiker_signature != second.duiker_signature
    write_culverts(sources[1], ["38"], [LineString([(1000, 1000), (1010, 1000)])])
    with pytest.raises(ValueError, match="nen3610id"):
        read_watersysteem_sources(*sources, spatial_selection=selection)


def test_culvert_spatial_selection_in_source_crs_preserves_full_geometry(sources):
    write_culverts(
        sources[0],
        ["30", "38"],
        [LineString([(0, 0), (100, 0)]), LineString([(200, 0), (300, 0)])],
    )
    source = wgpd.read_file(sources[0], layer="duikersifonhevel")
    source.to_crs(4326).to_file(sources[0], layer="duikersifonhevel")
    selected = read_watersysteem_sources(
        *sources, spatial_selection=box(-1, -1, 10, 10)
    )
    assert selected.culverts.bron_fid.tolist() == [1]
    assert selected.culverts.length.iloc[0] == pytest.approx(100, abs=0.01)


def test_culvert_source_wal_changes_preparation_identity(sources):
    from contextlib import closing
    import sqlite3

    write_culverts(sources[0], ["30"])
    with closing(sqlite3.connect(sources[0])) as connection:
        # Attribute-only update: satisfy the GeoPackage spatial-index trigger
        # guard without changing any geometry or its index bounds.
        connection.create_function("ST_IsEmpty", 1, lambda value: 0)
        connection.create_function("ST_MinX", 1, lambda value: 2)
        connection.create_function("ST_MaxX", 1, lambda value: 8)
        connection.create_function("ST_MinY", 1, lambda value: 0)
        connection.create_function("ST_MaxY", 1, lambda value: 0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        before = read_watersysteem_sources(
            *sources, spatial_selection=box(-1, -1, 100, 100)
        )
        connection.execute("UPDATE duikersifonhevel SET globalid='changed-in-wal'")
        connection.commit()
        after = read_watersysteem_sources(
            *sources, spatial_selection=box(-1, -1, 100, 100)
        )
        assert (
            before.culverts.attrs["source_identity"]
            != after.culverts.attrs["source_identity"]
        )
        assert before.culverts.globalid.tolist() != after.culverts.globalid.tolist()


def write_source(path, codes, categories, geometries, *, points=True, alias=False):
    category = "categorieoppervlaktewater" if alias else "categorieoppwaterlichaam"
    gpd.GeoDataFrame(
        {
            "nen3610id": [f"NL.WBHCODE.{code}.{i}" for i, code in enumerate(codes)],
            "globalid": [str(i) for i in range(len(codes))],
            category: categories,
        },
        geometry=geometries,
        crs=28992,
    ).to_file(path, layer="hydroobject")
    if points:
        gpd.GeoDataFrame({"nen3610id": []}, geometry=[], crs=28992).to_file(
            path, layer="duikersifonhevel"
        )
        for layer in ("gemaal", "stuw"):
            gpd.GeoDataFrame(
                {
                    "nen3610id": [
                        f"NL.WBHCODE.{code}.{i}" for i, code in enumerate(codes)
                    ]
                },
                geometry=[Point(line.coords[0]) for line in geometries],
                crs=28992,
            ).to_file(path, layer=layer)
    return path


@pytest.fixture
def sources(tmp_path):
    # A cross-authority secondary chain reaches only the RWS primary.
    gkw = write_source(
        tmp_path / "gkw.gpkg",
        ["30", "38", "80", "30", "38", "30"],
        ["primair", "primair", "primair", "secundair", "secundair", "secundair"],
        [
            LineString([(0, 0), (10, 0)]),
            LineString([(0, 10), (10, 10)]),
            LineString([(0, 80), (10, 80)]),
            LineString([(0, 30), (10, 30)]),
            LineString([(10, 30), (20, 30)]),
            LineString([(0, 60), (10, 60)]),
        ],
    )
    rws = write_source(
        tmp_path / "rws.gpkg",
        ["80"],
        ["primair"],
        [LineString([(20, 20), (20, 40)])],
        points=False,
        alias=True,
    )
    return gkw, rws


@pytest.mark.parametrize(
    "code,others,expected",
    [
        ("30", False, {"30"}),
        ("30", True, {"30", "38"}),
        (None, False, {"30", "38", "80"}),
    ],
)
def test_modes_joint_secondary_and_provenance(
    tmp_path, sources, code, others, expected
):
    selected = read_watersysteem_sources(
        *sources,
        spatial_selection=box(-5, -5, 100, 100),
        waterbeheercode=code,
        overige_waterschappen=others,
    )
    assert set(selected.targets.waterbeheercode) == expected
    assert set(selected.points.waterbeheercode) == expected
    assert len(selected.primary) == 3
    assert (
        selected.primary.bron_id.is_unique
    )  # Globalids and FIDs overlap across files.
    assert selected.primary.bron_fid.notna().all()
    rws = selected.primary.loc[selected.primary.waterbeheercode.eq("80")]
    assert rws.bronbestand.tolist() == [str(sources[1])]
    network = prepare_watersysteem(selected.targets, selected.points)
    path = write_watersysteem(
        hydroobject_primair=selected.primary,
        hydroobject_secundair=selected.secondary,
        watersysteem=network,
        output_path=tmp_path / "network.gpkg",
    )
    assert len(wgpd.read_file(path, layer="hydroobject_secundair")) == 2
    assert len(wgpd.read_file(path, layer="hydroobject_secundair_niet_verbonden")) == 1
    segments = wgpd.read_file(path, layer="hydroobject_segment")
    assert set(segments.waterbeheercode) == expected
    assert segments.segment_key.is_unique


@pytest.mark.parametrize("code", ["30", "38"])
@pytest.mark.parametrize("others", [False, True])
def test_complete_own_replacement_with_empty_structures(
    tmp_path, sources, code, others
):
    own = write_source(
        tmp_path / "own.gpkg", [code], ["primair"], [LineString([(0, 0), (100, 0)])]
    )
    for layer in ("gemaal", "stuw"):
        gpd.GeoDataFrame({"nen3610id": []}, geometry=[], crs=28992).to_file(
            own, layer=layer
        )
    selected = read_watersysteem_sources(
        *sources,
        spatial_selection=box(-1, -1, 25, 90),
        waterbeheercode=code,
        overige_waterschappen=others,
        eigen_hydamo=own,
    )
    own_primary = selected.primary.loc[selected.primary.waterbeheercode.eq(code)]
    assert own_primary.bronbestand.tolist() == [str(own)]
    assert own_primary.geometry.iloc[0].length == 100  # No clipping.
    assert not selected.secondary.waterbeheercode.eq(code).any()
    assert not selected.points.waterbeheercode.eq(code).any()


@pytest.mark.parametrize(
    "identifier", [None, "wrong", "NL.WBHCODE.38.x", "NL.WBHCODE.30."]
)
def test_own_identifiers_checked_outside_selection(tmp_path, sources, identifier):
    own = write_source(
        tmp_path / "own.gpkg",
        ["30"],
        ["primair"],
        [LineString([(1000, 1000), (1010, 1000)])],
    )
    frame = wgpd.read_file(own, layer="gemaal")
    frame["nen3610id"] = identifier
    frame.to_file(own, layer="gemaal")
    with pytest.raises(ValueError, match="nen3610id"):
        read_watersysteem_sources(
            *sources,
            spatial_selection=box(0, 0, 10, 10),
            waterbeheercode="30",
            eigen_hydamo=own,
        )


def test_missing_own_layer_and_unknown_category(tmp_path, sources):
    own = write_source(
        tmp_path / "own.gpkg",
        ["30"],
        ["primair"],
        [LineString([(0, 0), (10, 0)])],
        points=False,
    )
    with pytest.raises(ValueError, match="missing required layers"):
        read_watersysteem_sources(
            *sources,
            spatial_selection=box(-5, -5, 100, 100),
            waterbeheercode="30",
            eigen_hydamo=own,
        )
    frame = wgpd.read_file(sources[1], layer="hydroobject")
    frame["categorieoppervlaktewater"] = "unknown"
    frame.to_file(sources[1], layer="hydroobject")
    with pytest.raises(ValueError, match="unknown or missing"):
        read_watersysteem_sources(*sources, spatial_selection=box(-5, -5, 100, 100))


def test_known_crs_transformed(tmp_path, sources):
    frame = wgpd.read_file(sources[1], layer="hydroobject")
    frame.to_crs(4326).to_file(sources[1], layer="hydroobject")
    selected = read_watersysteem_sources(
        *sources, spatial_selection=box(-5, -5, 100, 100)
    )
    rws = selected.primary.loc[selected.primary.waterbeheercode.eq("80")]
    assert rws.crs.to_epsg() == 28992
    assert (
        rws.geometry.iloc[0].hausdorff_distance(LineString([(20, 20), (20, 40)])) < 0.01
    )


def test_missing_crs_rejected(sources):
    frame = wgpd.read_file(sources[1], layer="hydroobject")
    frame = frame.set_crs(None, allow_override=True)
    with pytest.warns(UserWarning, match="crs"):
        frame.to_file(sources[1], layer="hydroobject")
    with pytest.raises(ValueError, match="CRS"):
        read_watersysteem_sources(*sources, spatial_selection=box(-5, -5, 100, 100))


@pytest.mark.parametrize("code,others", [("30", False), ("30", True), (None, False)])
def test_gkw_missing_category_is_visible_but_never_burned(
    tmp_path, sources, caplog, code, others
):
    frame = wgpd.read_file(sources[0], layer="hydroobject")
    frame.loc[3:5, "categorieoppwaterlichaam"] = ["overig", "tertiair", None]
    frame.to_file(sources[0], layer="hydroobject")
    selected = read_watersysteem_sources(
        *sources,
        spatial_selection=box(-5, -5, 100, 100),
        waterbeheercode=code,
        overige_waterschappen=others,
    )
    assert len(selected.primary) == 3
    assert selected.secondary.empty
    assert len(selected.missing_category) == 1
    assert selected.missing_category.bron_fid.tolist() == [6]
    assert selected.missing_category.nen3610id.tolist() == ["NL.WBHCODE.30.5"]
    assert "without a category" in caplog.text
    network = prepare_watersysteem(selected.targets, selected.points)
    options = dict(
        hydroobject_primair=selected.primary,
        hydroobject_secundair=selected.secondary,
        watersysteem=network,
        output_path=tmp_path / "network.gpkg",
    )
    # Inspection output is refreshed independently of the reusable watersysteem.
    write_watersysteem(**options)
    path = write_watersysteem(
        **options, hydroobject_zonder_categorie=selected.missing_category
    )
    assert "hydroobject_zonder_categorie" not in set(gpd.list_layers(path)["name"])
    control_path = tmp_path / "controle.gpkg"
    control = wgpd.read_file(control_path, layer="hydroobject_zonder_categorie")
    assert control.bronbestand.tolist() == [str(sources[0])]
    assert control.bron_fid.tolist() == [6]
    assert control.uitsluitreden.tolist() == ["categorie ontbreekt"]
    assert control.categorieoppwaterlichaam.isna().all()
    write_watersysteem(**options)
    assert wgpd.read_file(control_path, layer="hydroobject_zonder_categorie").empty


def test_conflicting_categories_rejected(sources):
    frame = wgpd.read_file(sources[1], layer="hydroobject")
    frame["categorieoppwaterlichaam"] = "secundair"
    frame.to_file(sources[1], layer="hydroobject")
    with pytest.raises(ValueError, match="conflicting category"):
        read_watersysteem_sources(*sources, spatial_selection=box(-5, -5, 100, 100))


def test_target_switch_keeps_burned_dem_and_changes_segment_raster(tmp_path, sources):
    ahn = tmp_path / "ahn.tif"
    with rasterio.open(
        ahn,
        "w",
        driver="GTiff",
        height=90,
        width=90,
        count=1,
        dtype="float32",
        crs=28992,
        transform=rasterio.transform.from_origin(-5, 95, 1, 1),
        nodata=-9999,
    ) as dest:
        data = np.full((90, 90), 5, dtype="float32")
        dest.write(data, 1)
    results = []
    for others in (False, True):
        selected = read_watersysteem_sources(
            *sources,
            spatial_selection=box(-5, -5, 95, 95),
            waterbeheercode="30",
            overige_waterschappen=others,
        )
        network = prepare_watersysteem(selected.targets, selected.points)
        path = write_watersysteem(
            hydroobject_primair=selected.primary,
            hydroobject_secundair=selected.secondary,
            watersysteem=network,
            output_path=tmp_path / f"network_{others}.gpkg",
        )
        results.append(
            prepare_watersysteem_rasters(
                box(-5, -5, 95, 95),
                burn_depth_m=100,
                ahn_vrt_path=ahn,
                watersysteem_path=path,
                output_dir=tmp_path / str(others),
                resolution_m=1,
            )
        )
    with (
        rasterio.open(results[0].dem_path) as a,
        rasterio.open(results[1].dem_path) as b,
    ):
        np.testing.assert_array_equal(a.read(1), b.read(1))
        assert a.read(1)[99, 99] == a.nodata
    with (
        rasterio.open(results[0].hydroobject_segment_path) as a,
        rasterio.open(results[1].hydroobject_segment_path) as b,
    ):
        assert np.count_nonzero(a.read(1)) < np.count_nonzero(b.read(1))


@pytest.mark.parametrize(
    "code,others,expected",
    [
        ("30", False, {"30"}),
        ("30", True, {"30", "38"}),
        (None, False, {"30", "38", "80"}),
    ],
)
def test_real_pcraster_assigns_only_participating_authorities(
    tmp_path, sources, code, others, expected
):
    pcraster = pytest.importorskip("pcraster")
    pcraster.setrandomseed(12345)
    ahn = tmp_path / "dem.tif"
    with rasterio.open(
        ahn,
        "w",
        driver="GTiff",
        height=100,
        width=100,
        count=1,
        dtype="float32",
        crs=28992,
        transform=rasterio.transform.from_origin(-5, 95, 1, 1),
    ) as dest:
        dest.write(np.full((100, 100), 5, dtype="float32"), 1)
    selected = read_watersysteem_sources(
        *sources,
        spatial_selection=box(-5, -5, 95, 95),
        waterbeheercode=code,
        overige_waterschappen=others,
    )
    network = prepare_watersysteem(selected.targets, selected.points)
    path = write_watersysteem(
        hydroobject_primair=selected.primary,
        hydroobject_secundair=selected.secondary,
        watersysteem=network,
        output_path=tmp_path / "network.gpkg",
    )
    rasters = prepare_watersysteem_rasters(
        box(-5, -5, 95, 95),
        burn_depth_m=100,
        ahn_vrt_path=ahn,
        watersysteem_path=path,
        output_dir=tmp_path / "rasters",
        resolution_m=1,
    )
    result = calculate_subcatchments(rasters, watersysteem_path=path)
    units = result.subcatchments.merge(
        network.hydroobject_segmenten[["segment_key", "waterbeheercode"]],
        on="segment_key",
    )
    assert set(units.waterbeheercode) == expected


def test_category_overrides_authority_and_optional_priority(tmp_path):
    gkw = write_source(
        tmp_path / "gkw.gpkg",
        ["30", "30", "38"],
        ["primair", "secundair", "secundair"],
        [
            LineString([(0, 5), (10, 5)]),
            LineString([(15, 0), (15, 10)]),
            LineString([(5, 0), (5, 10)]),
        ],
    )
    rws = write_source(
        tmp_path / "rws.gpkg",
        ["80"],
        ["primair"],
        [LineString([(10, 5), (20, 5)])],
        points=False,
        alias=True,
    )
    selected = read_watersysteem_sources(
        gkw, rws, spatial_selection=box(0, 0, 20, 20), waterbeheercode="30"
    )
    network = prepare_watersysteem(selected.targets, selected.points)
    path = write_watersysteem(
        hydroobject_primair=selected.primary,
        hydroobject_secundair=selected.secondary,
        watersysteem=network,
        output_path=tmp_path / "network.gpkg",
    )
    ahn = tmp_path / "dem.tif"
    with rasterio.open(
        ahn,
        "w",
        driver="GTiff",
        height=20,
        width=20,
        count=1,
        dtype="float32",
        crs=28992,
        transform=rasterio.transform.from_origin(0, 20, 1, 1),
    ) as dest:
        dest.write(np.full((20, 20), 5, dtype="float32"), 1)
    optional = tmp_path / "optional.gpkg"
    gpd.GeoDataFrame(geometry=[box(0, 0, 20, 20)], crs=28992).to_file(
        optional, layer="raise"
    )
    rasters = prepare_watersysteem_rasters(
        box(0, 0, 20, 20),
        burn_depth_m=100,
        ahn_vrt_path=ahn,
        watersysteem_path=path,
        output_dir=tmp_path / "rasters",
        resolution_m=1,
        brandlagen=BrandlagenConfig(
            (Brandlaag(optional, "raise"),), brandwaarde=7, prioriteit=999999
        ),
    )
    with rasterio.open(rasters.dem_path) as dem:
        values = dem.read(1)
    assert values[15, 15] == -195  # RWS primary over own secondary; no addition.
    assert values[15, 5] == -195  # Own primary over external secondary.
    assert values[12, 15] == -95
    assert values[12, 5] == -95
    assert values[1, 1] == 12
