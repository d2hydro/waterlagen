"""Authority replacement and burn context use real small GeoPackages."""

import geopandas as gpd
import numpy as np
import pytest
import rasterio
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
    assert segments.segment_id.is_unique


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
        network.hydroobject_segmenten[["segment_id", "waterbeheercode"]],
        on="segment_id",
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
