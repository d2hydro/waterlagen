"""Joint water/culvert policy, tested independently from terrain interpolation."""

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from shapely.geometry import LineString, box

from waterlagen.afwateringseenheden.config import (
    BrandlagenConfig,
    read_brandlagen_config,
)
from waterlagen.afwateringseenheden.sources import WatersysteemSources
from waterlagen.afwateringseenheden.waternet import (
    _classify_culverts,
    prepare_waternet,
    read_waternet,
)
from waterlagen.raster.grid import RasterGrid
from waterlagen.settings import settings


def frame(geometries=()):
    return gpd.GeoDataFrame(geometry=list(geometries), crs=settings.crs)


def sources(primary=(), secondary=(), tertiary=(), culverts=()):
    duikers = frame(culverts)
    duikers["bronbestand"] = "hydamo.gpkg"
    duikers["bronlaag"] = "duikersifonhevel"
    duikers["bron_fid"] = range(len(duikers))
    duikers["bron_id"] = [f"hydamo-{i}" for i in range(len(duikers))]
    return WatersysteemSources(
        frame(primary),
        frame(secondary),
        frame(primary),
        frame(),
        culverts=duikers,
        tertiary=frame(tertiary),
    )


def optional(geometries=(), roles=(), origins=()):
    result = frame(geometries)
    result["broncode"] = np.arange(3, len(result) + 3)
    result["rol"] = list(roles)
    result["bron"] = list(origins)
    result["bronbestand"] = "optional.gpkg"
    result["bronlaag"] = "objects"
    result["bron_fid"] = range(len(result))
    return result


def grid(bounds=(0, 0, 40, 40)):
    return RasterGrid.from_bounds(bounds, resolution=2, crs=settings.crs)


def line(*points):
    return LineString(points)


def prepare(tmp_path, data, extra=None, grids=None, primary_pieces=None):
    network = tmp_path / "watersysteem.gpkg"
    network.write_text("test input identity")
    grids = grids or [grid()]
    prepare_waternet(
        data,
        optional() if extra is None else extra,
        grids,
        network,
        BrandlagenConfig(waternet=True, geisoleerde_branddiepte_m=10),
        primary_culvert_pieces=primary_pieces,
    )
    return network


def cell(raster_grid, x, y):
    col, row = ~raster_grid.transform * (x, y)
    return int(row), int(col)


def test_primary_culvert_blocks_optional_water_without_rws_stop(tmp_path):
    data = sources(
        primary=[line((1, 21), (39, 21))], culverts=[line((11, 21), (29, 21))]
    )
    # The primary context also represents RWS: the target subset may be empty.
    data.targets.drop(data.targets.index, inplace=True)
    extra = optional([box(9, 19, 31, 23)], ["water"], [None])
    network = prepare(tmp_path, data, extra)
    treatment, codes, excluded, _, _ = read_waternet(network, grid())
    middle = cell(grid(), 21, 21)
    assert treatment[middle] == 4
    assert codes[middle] == 0
    assert excluded[middle]
    assert treatment[cell(grid(), 3, 21)] == 1


def test_secondary_side_connection_inside_primary_culvert(tmp_path):
    data = sources(
        primary=[line((1, 21), (39, 21))],
        secondary=[line((25, 37), (25, 21))],
        culverts=[line((11, 21), (29, 21))],
    )
    classified = _classify_culverts(data, optional(), grid())
    assert classified.behandeling.tolist() == ["aanvoer"]
    network = prepare(tmp_path, data)
    treatment, _, excluded, _, _ = read_waternet(network, grid())
    assert treatment[cell(grid(), 21, 21)] == 2
    assert treatment[cell(grid(), 25, 31)] == 2
    assert excluded[cell(grid(), 21, 21)]


def test_secondary_crossing_without_endpoint_does_not_reclassify_primary_culvert():
    data = sources(
        primary=[line((1, 21), (39, 21))],
        secondary=[line((21, 1), (21, 39))],
        culverts=[line((11, 21), (29, 21))],
    )
    classified = _classify_culverts(data, optional(), grid())
    assert classified.behandeling.tolist() == ["primair_primair"]


@pytest.mark.parametrize("kind", ["secondary", "tertiary"])
@pytest.mark.parametrize("connected", [False, True])
def test_isolated_and_connected_lower_networks(tmp_path, kind, connected):
    lower = [line((1, 21), (11, 21)), line((21, 21), (37, 21))]
    data = sources(
        primary=[line((37, 1), (37, 39))] if connected else [],
        culverts=[line((11, 21), (21, 21))],
        **{kind: lower},
    )
    network = prepare(tmp_path, data)
    treatment, _, excluded, _, shallow = read_waternet(network, grid())
    expected = 2 if connected and kind == "secondary" else 3
    assert treatment[cell(grid(), 15, 21)] == expected
    assert treatment[cell(grid(), 5, 21)] == expected
    assert np.all(shallow == 10)
    assert excluded[cell(grid(), 15, 21)]


def test_unconnected_culvert_is_control_only(tmp_path):
    data = sources(culverts=[line((11, 21), (21, 21))])
    classified = _classify_culverts(data, optional(), grid())
    assert classified.behandeling.tolist() == ["controle"]
    network = prepare(tmp_path, data)
    treatment, _, excluded, _, _ = read_waternet(network, grid())
    assert not treatment.any()
    assert not excluded.any()


def test_bgt_polygon_connects_without_centerline_derivation(tmp_path):
    data = sources(secondary=[line((1, 21), (11, 21)), line((21, 21), (37, 21))])
    extra = optional([box(10, 20, 22, 22)], ["duiker"], ["bgt"])
    classified = _classify_culverts(data, extra, grid())
    assert classified.behandeling.tolist() == ["aanvoer"]
    network = prepare(tmp_path, data, extra)
    treatment, _, excluded, _, _ = read_waternet(network, grid())
    assert treatment[cell(grid(), 15, 21)] == 3
    assert excluded[cell(grid(), 15, 21)]


def test_source_preference_retains_provenance_and_does_not_merge_crossings():
    geometry = line((11, 21), (29, 21))
    data = sources(primary=[line((1, 21), (39, 21))], culverts=[geometry])
    extra = optional(
        [box(11, 20, 29, 22), geometry, line((21, 11), (21, 31))],
        ["duiker"] * 3,
        ["bgt", "osm", "osm"],
    )
    classified = _classify_culverts(data, extra, grid())
    assert classified.behandeling.tolist() == [
        "primair_primair",
        "dubbel",
        "dubbel",
        "controle",
    ]
    assert classified.voorkeur_id.tolist()[1:3] == ["hydamo-0", "hydamo-0"]


def test_components_connect_across_overlapping_tile_buffers(tmp_path):
    first = grid((0, 0, 40, 40))
    second = grid((30, 0, 70, 40))
    data = sources(
        primary=[line((63, 1), (63, 39))], secondary=[line((1, 21), (63, 21))]
    )
    network = prepare(tmp_path, data, grids=[first, second])
    treatment, _, _, _, _ = read_waternet(network, first)
    assert treatment[cell(first, 5, 21)] == 2


def test_overlap_water_is_shallow_with_isolated_hydamo(tmp_path):
    data = sources(secondary=[line((1, 21), (37, 21))])
    extra = optional([box(1, 17, 37, 25)], ["water"], [None])
    network = prepare(tmp_path, data, extra)
    treatment, _, _, _, _ = read_waternet(network, grid())
    assert treatment[cell(grid(), 5, 21)] == 3
    assert treatment[cell(grid(), 5, 19)] == 3


def test_connected_additional_water_and_tertiary_remain_shallow(tmp_path):
    data = sources(
        primary=[line((37, 1), (37, 39))],
        secondary=[line((1, 21), (37, 21))],
        tertiary=[line((1, 11), (37, 11))],
    )
    extra = optional([box(1, 17, 37, 25)], ["water"], [None])
    network = prepare(tmp_path, data, extra)
    treatment, codes, _, _, shallow = read_waternet(network, grid())
    assert treatment[cell(grid(), 5, 21)] == 2
    assert codes[cell(grid(), 5, 21)] == 2
    assert treatment[cell(grid(), 5, 19)] == 3
    assert treatment[cell(grid(), 5, 11)] == 3
    assert treatment[cell(grid(), 37, 21)] == 1
    assert np.all(shallow == 10)


@pytest.mark.parametrize("origin", ["bgt", "osm"])
def test_connected_additional_culvert_remains_shallow(tmp_path, origin):
    data = sources(
        primary=[line((37, 1), (37, 39))],
        secondary=[line((1, 21), (11, 21)), line((21, 21), (37, 21))],
    )
    extra = optional([line((11, 21), (21, 21))], ["duiker"], [origin])
    network = prepare(tmp_path, data, extra)
    treatment, _, excluded, _, _ = read_waternet(network, grid())
    assert treatment[cell(grid(), 15, 21)] == 3
    assert excluded[cell(grid(), 15, 21)]
    # A shallow connection cannot turn an otherwise isolated secondary into
    # a 100 m depression whose only exit has been lowered by just 10 m.
    assert treatment[cell(grid(), 5, 21)] == 3
    assert treatment[cell(grid(), 29, 21)] == 2


def test_optional_water_does_not_promote_isolated_hydamo_to_deep(tmp_path):
    data = sources(
        primary=[line((37, 1), (37, 39))], secondary=[line((1, 21), (11, 21))]
    )
    extra = optional([box(9, 19, 37, 23)], ["water"], [None])
    network = prepare(tmp_path, data, extra)
    treatment, _, _, _, _ = read_waternet(network, grid())
    assert treatment[cell(grid(), 5, 21)] == 3
    assert treatment[cell(grid(), 23, 21)] == 3


@pytest.mark.parametrize("origin", ["bgt", "osm"])
def test_shallow_culvert_cannot_overwrite_deep_hydamo_connection(tmp_path, origin):
    data = sources(
        primary=[line((37, 1), (37, 39))],
        secondary=[
            line((1, 21), (11, 21)),
            line((29, 21), (37, 21)),
            line((21, 1), (21, 11)),
            line((21, 31), (21, 39)),
        ],
        culverts=[line((11, 21), (29, 21))],
    )
    # A crossing culvert is not a source duplicate; precedence must still hold.
    extra = optional(
        [line((21, 11), (21, 31)), box(1, 19, 39, 23)],
        ["duiker", "water"],
        [origin, None],
    )
    network = prepare(tmp_path, data, extra)
    treatment, codes, excluded, _, _ = read_waternet(network, grid())
    assert treatment[cell(grid(), 21, 21)] == 2
    assert codes[cell(grid(), 21, 21)] == 5  # HYDAMO culvert, after optional codes.
    assert excluded[cell(grid(), 21, 21)]
    assert treatment[cell(grid(), 21, 15)] == 3
    assert codes[cell(grid(), 21, 15)] == 3
    assert treatment[cell(grid(), 5, 21)] == 2
    assert treatment[cell(grid(), 5, 19)] == 3


def test_secondary_tertiary_hydamo_culvert_is_not_deep(tmp_path):
    data = sources(
        primary=[line((37, 1), (37, 39))],
        secondary=[line((1, 21), (11, 21))],
        tertiary=[line((21, 21), (37, 21))],
        culverts=[line((11, 21), (21, 21))],
    )
    classified = _classify_culverts(data, optional(), grid())
    assert classified.behandeling.tolist() == ["aanvoer"]
    assert not classified.diep_geschikt.any()
    network = prepare(tmp_path, data)
    treatment, _, _, _, _ = read_waternet(network, grid())
    assert treatment[cell(grid(), 15, 21)] == 3


def test_configured_shallow_depths_and_hydamo_precedence(tmp_path):
    data = sources(
        primary=[line((37, 1), (37, 39))], secondary=[line((1, 21), (37, 21))]
    )
    extra = optional(
        [box(1, 15, 19, 25), box(21, 15, 35, 25)],
        ["water", "water"],
        [None, None],
    )
    extra["brandwaarde"] = [-10.0, -5.0]
    extra["prioriteit"] = [2, 1]
    network = prepare(tmp_path, data, extra)
    treatment, _, _, _, depths = read_waternet(network, grid())
    assert depths[cell(grid(), 5, 17)] == 10
    assert depths[cell(grid(), 25, 17)] == 5
    assert treatment[cell(grid(), 5, 21)] == 2
    assert treatment[cell(grid(), 25, 21)] == 2


@pytest.mark.parametrize("side_connection", [False, True])
def test_matched_primary_piece_leaves_no_deep_cells_beside_culvert(
    tmp_path, side_connection
):
    # Real geometry from duiker 511500: a redundant primary vertex changes two
    # raster cells compared with the straight culvert line (unassigned FID 118).
    start = (174209.684, 393706.747000001)
    middle = (174207.559900001, 393716.057300001)
    end = (174199.592, 393750.982000001)
    data = sources(
        primary=[line((174214, 393690), start, middle, end, (174195, 393770))],
        secondary=[line((174235, 393716), middle)] if side_connection else [],
        culverts=[line(start, end)],
    )
    pieces = frame(
        [
            line((174214, 393690), start),
            line(start, middle, end),
            line(end, (174195, 393770)),
        ]
    )
    pieces["duiker_ids"] = ["[]", '["hydamo-0"]', "[]"]
    pieces["brandgeschikt"] = [True, False, True]
    local = grid((174180, 393680, 174240, 393780))
    network = prepare(tmp_path, data, grids=[local], primary_pieces=pieces)
    treatment, codes, excluded, _, _ = read_waternet(network, local)
    for x, y in [(174205, 393729), (174207, 393721)]:
        point = cell(local, x, y)
        assert treatment[point] == (2 if side_connection else 4)
        assert codes[point] != 1
        assert excluded[point]


@pytest.mark.parametrize("side_connection", [False, True])
def test_reversed_culvert_keeps_both_raster_footprints(tmp_path, side_connection):
    # FID 162: identical line endpoints in opposite order rasterize differently.
    start = (186881.011999998, 380977.539999999)
    end = (186888.124000002, 380961.515000001)
    before = (186895, 380945)
    after = (186873, 380995)
    data = sources(
        primary=[line(before, end, start, after)],
        secondary=[line((186910, 380961), end)] if side_connection else [],
        culverts=[line(start, end)],
    )
    pieces = frame([line(before, end), line(end, start), line(start, after)])
    pieces["brandgeschikt"] = [True, False, True]
    pieces["duiker_ids"] = ["[]", '["hydamo-0"]', "[]"]
    local = grid((186860, 380940, 186920, 381000))
    network = prepare(tmp_path, data, grids=[local], primary_pieces=pieces)
    treatment, codes, excluded, _, _ = read_waternet(network, local)
    for x, y in [(186881, 380975), (186883, 380971), (186885, 380967)]:
        point = cell(local, x, y)
        assert treatment[point] == (2 if side_connection else 4)
        assert codes[point] != 1
        assert excluded[point]


def test_prepared_primary_pieces_do_not_leave_full_line_raster_cells(tmp_path):
    # FID 206: rasterizing a full line is not equivalent to rasterizing its parts.
    before = (195845.5407, 403641.777199999)
    start = (195845.75333401345, 403642.0782759771)
    end = (195869.863000002, 403676.215999998)
    after = (195889.083000001, 403694.572999999)
    data = sources(
        primary=[line(before, end, after)],
        culverts=[line((195845.7533, 403642.078299999), end)],
    )
    pieces = frame([line(before, start), line(start, end), line(end, after)])
    pieces["brandgeschikt"] = [True, False, True]
    pieces["duiker_ids"] = ["[]", '["hydamo-0"]', "[]"]
    local = grid((195820, 403620, 195900, 403700))
    network = prepare(tmp_path, data, grids=[local], primary_pieces=pieces)
    treatment, codes, _, _, _ = read_waternet(network, local)
    for x, y in [(195859, 403661), (195855, 403655), (195849, 403647)]:
        point = cell(local, x, y)
        assert treatment[point] in (0, 4)
        assert codes[point] == 0


@pytest.mark.parametrize("side_connection", [False, True])
def test_culvert_preserves_crossing_allowed_primary_and_secondary(
    tmp_path, side_connection
):
    main = line((1, 21), (39, 21))
    crossing = line((21, 1), (21, 39))
    secondary_crossing = line((15, 1), (15, 39))
    secondary = [secondary_crossing]
    if side_connection:
        secondary.append(line((25, 37), (25, 21)))
    data = sources(
        primary=[main, crossing],
        secondary=secondary,
        culverts=[line((11, 21), (29, 21))],
    )
    pieces = frame(
        [
            line((1, 21), (11, 21)),
            line((11, 21), (29, 21)),
            line((29, 21), (39, 21)),
            crossing,
        ]
    )
    pieces["brandgeschikt"] = [True, False, True, True]
    pieces["duiker_ids"] = ["[]", '["hydamo-0"]', "[]", "[]"]
    network = prepare(tmp_path, data, primary_pieces=pieces)
    treatment, codes, excluded, _, _ = read_waternet(network, grid())
    point = cell(grid(), 21, 21)
    assert treatment[point] == 1
    assert codes[point] == 1
    assert not excluded[point]
    assert treatment[cell(grid(), 15, 21)] == (2 if side_connection else 3)
    assert codes[cell(grid(), 15, 21)] != 0


def test_waternet_config_roles(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "waternet = true\ngeisoleerde_branddiepte_m = 10\n"
        '[[lagen]]\npath="bgt.gpkg"\nlayer="duikers"\nrol="duiker"\nbron="bgt"\n'
    )
    config = read_brandlagen_config(path)
    assert config.waternet
    assert config.lagen[0].bron == "bgt"
    path.write_text(path.read_text().replace("waternet = true", "waternet = false"))
    with pytest.raises(ValueError, match="require waternet"):
        read_brandlagen_config(path)


def test_stale_preparation_is_rejected(tmp_path):
    network = prepare(tmp_path, sources())
    network.write_text("different input")
    with pytest.raises(ValueError, match="stale"):
        read_waternet(network, grid())


def test_side_connection_reaches_primary_target_through_burned_culvert(tmp_path):
    from waterlagen.afwateringseenheden import prepare_watersysteem_rasters
    from waterlagen.afwateringseenheden.pcraster import calculate_subcatchments

    data = sources(
        primary=[line((1, 21), (39, 21))],
        secondary=[line((25, 37), (25, 21))],
        culverts=[line((11, 21), (29, 21))],
    )
    network = tmp_path / "watersysteem.gpkg"
    data.primary.to_file(network, layer="hydroobject_primair")
    data.secondary.to_file(network, layer="hydroobject_secundair")
    targets = data.primary.copy()
    targets["segment_key"] = ["primary"]
    targets.to_file(network, layer="hydroobject_segment")
    ahn = tmp_path / "dem.tif"
    with rasterio.open(
        ahn,
        "w",
        driver="GTiff",
        width=20,
        height=20,
        count=1,
        dtype="float32",
        nodata=-9999,
        crs=settings.crs,
        transform=grid().transform,
    ) as target:
        target.write(np.full((20, 20), 10, dtype="float32"), 1)
    extra = optional(
        [box(1, 27, 19, 39), box(21, 27, 39, 39)],
        ["water", "water"],
        [None, None],
    )
    extra["brandwaarde"] = [-10.0, -5.0]
    extra["prioriteit"] = [2, 1]
    prepare_waternet(data, extra, [grid()], network, BrandlagenConfig(waternet=True))
    rasters = prepare_watersysteem_rasters(
        box(0, 0, 40, 40),
        burn_depth_m=100,
        ahn_vrt_path=ahn,
        watersysteem_path=network,
        output_dir=tmp_path / "result",
    )
    result = calculate_subcatchments(rasters, watersysteem_path=network)
    with rasterio.open(result.subcatchments_path) as source:
        assert source.read(1)[cell(grid(), 25, 31)] == 1
    with rasterio.open(rasters.hydroobject_segment_path) as source:
        assert source.read(1)[cell(grid(), 25, 21)] == 0
    with rasterio.open(rasters.dem_path) as source:
        elevations = source.read(1) * source.scales[0]
        assert elevations[cell(grid(), 5, 31)] == 0  # BGT: 10 - 10.
        assert elevations[cell(grid(), 33, 31)] == 5  # TOP10NL: 10 - 5.
        assert elevations[cell(grid(), 25, 31)] == -90  # Protected HYDAMO.
