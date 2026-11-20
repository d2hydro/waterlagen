"""Meerdere waterschappen vormen één gebied, met complete tegels en buurten."""

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from waterlagen import areas
from waterlagen._sources import SourcePreparation
from waterlagen.administratieve_gebieden.download import WATERSCHAPSGRENZEN_FILENAME
from waterlagen.datastore import DataStore


@pytest.fixture
def authority_areas(tmp_path):
    store = DataStore(data_dir=tmp_path, _env_file=None)
    notch = box(109999, 405000, 110001, 405001)
    geometry = [
        box(100000, 400000, 110000, 410000).difference(notch),
        box(110000, 400000, 120000, 410000).difference(notch),
        box(140000, 400000, 150000, 410000),
    ]
    frame = gpd.GeoDataFrame(
        {
            "naam": ["Eerste", "Tweede", "Los gebied"],
            "code": ["12", "13", "38"],
            "waterbeheerdercode": ["12", "13", "38"],
            "nen3610id": ["one", "two", "three"],
        },
        geometry=geometry,
        crs=28992,
    )
    frame.to_file(
        store.administratieve_gebieden_dir / WATERSCHAPSGRENZEN_FILENAME,
        layer="waterschap",
    )
    return store, frame, notch


@pytest.mark.parametrize(
    "value", ["13,12,12", "12,13", "waterschappen_13_12", " 12 , 13 "]
)
def test_combined_area_has_stable_identity_and_preserves_small_holes(
    authority_areas, value
):
    store, frame, notch = authority_areas
    area = areas.resolve_area(value, store, SourcePreparation(offline=True))
    assert area.value == "waterschappen_12_13"
    assert areas.area_authority_codes(area) == ("12", "13")
    assert area.geometry.equals(frame.iloc[:2].geometry.union_all())
    assert area.geometry.intersection(notch).area == 0
    expected = areas.resolve_area("12,13", store, SourcePreparation(offline=True))
    assert area.identity == expected.identity


def test_disconnected_areas_do_not_include_the_space_between(authority_areas):
    store, frame, _ = authority_areas
    area = areas.resolve_area("38,12", store, SourcePreparation(offline=True))
    assert area.geometry.equals(frame.iloc[[0, 2]].geometry.union_all())
    assert area.geometry.geom_type == "MultiPolygon"
    assert not area.geometry.covers(Point(130000, 405000))


def test_unknown_code_does_not_produce_a_partial_selection(authority_areas):
    store, _, _ = authority_areas
    with pytest.raises(ValueError, match="999"):
        areas.resolve_area("12,999", store, SourcePreparation(offline=True))


@pytest.mark.parametrize(
    "value", ["12,", ",12", "12;13", "12,x", "12/13", "", "12,-13"]
)
def test_invalid_multiple_codes_are_rejected(value):
    with pytest.raises(ValueError):
        areas.area_name(value)


def test_one_authority_keeps_its_existing_run_folder(authority_areas):
    store, frame, _ = authority_areas
    for value in ("12", "12,12", "waterschap_12"):
        area = areas.resolve_area(value, store, SourcePreparation(offline=True))
        assert area.value == "waterschap_12"
        assert area.geometry.equals(frame.geometry.iloc[0])


def test_complete_tiles_cover_both_authorities_and_the_small_sliver(authority_areas):
    store, _, notch = authority_areas
    area = areas.resolve_area("12,13", store, SourcePreparation(offline=True))
    tiles = gpd.GeoDataFrame(
        {
            "tile_id": ["left", "right", "outside"],
            "xmin": [100000, 110000, 120000],
            "ymin": [400000] * 3,
        },
        geometry=[box(x, 400000, x + 10000, 410000) for x in (100000, 110000, 120000)],
        crs=28992,
    )
    selected = areas.select_area_tiles(tiles, area)
    assert selected.tile_id.tolist() == ["left", "right"]
    assert selected.tile_id.is_unique
    assert selected.geometry.area.tolist() == [100_000_000, 100_000_000]
    assert selected.geometry.union_all().covers(notch)


def test_cbs_selection_keeps_addresses_in_a_small_boundary_hole(
    authority_areas, tmp_path, monkeypatch
):
    from waterlagen import _cbs_production as cbs

    store, _, _ = authority_areas
    area = areas.resolve_area("12,13", store, SourcePreparation(offline=True))
    buurten = gpd.GeoDataFrame(
        {"buurtcode": ["inside", "outside"]},
        geometry=[
            box(109990, 404990, 110010, 405010),
            box(150000, 400000, 150010, 400010),
        ],
        crs=28992,
    )
    bag = gpd.GeoDataFrame(
        {"buurtcode": ["inside", "outside"]},
        geometry=[Point(110000, 405000.5), Point(150005, 400005)],
        crs=28992,
    )
    monkeypatch.setattr(
        cbs,
        "read_file",
        lambda path, **kwargs: buurten if path.name == "buurten.gpkg" else bag,
    )
    outputs = {}
    monkeypatch.setattr(
        cbs,
        "write_geopackage_layer_atomically",
        lambda data, path, **kwargs: outputs.update({path.name: data.copy()}),
    )
    cbs.select_buurt_context(
        tmp_path / "bag.gpkg", tmp_path / "buurten.gpkg", area, tmp_path / "selected"
    )
    assert outputs["bag_vbo.gpkg"].buurtcode.tolist() == ["inside"]
    assert outputs["cbs_buurt.gpkg"].geometry.iloc[0].equals(buurten.geometry.iloc[0])
