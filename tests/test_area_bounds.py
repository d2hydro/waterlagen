import math

import geopandas as gpd
import pytest
from shapely.geometry import box

from waterlagen._sources import SourcePreparation
from waterlagen.areas import (
    ProductionArea,
    area_from_bounds,
    area_name,
    resolve_area,
    select_area_tiles,
)
from waterlagen.datastore import DataStore


def test_canonical_names_preserve_coordinates():
    first = area_from_bounds((-0.0, -1.5, 1, 2))
    equivalent = area_from_bounds((0, -1.50, 1.0, 2.0))
    assert first.value == equivalent.value == "0_-1.5_1_2"
    assert first.identity == equivalent.identity
    assert area_name(first) == first.value
    adjacent = area_from_bounds((0, -1.5, math.nextafter(1, 2), 2))
    assert adjacent.value != first.value
    assert adjacent.identity != first.identity
    assert area_from_bounds((1e-7, 0, 1, 2)).value == "0.0000001_0_1_2"
    with pytest.raises(ValueError, match="Onbekend gebied"):
        area_name(first.value)  # Coordinate names are not a new --area syntax.


@pytest.mark.parametrize(
    "bounds",
    [
        (1, 2, 3),
        (0, 0, 0, 1),
        (2, 0, 1, 1),
        (0, 2, 1, 1),
        (0, 0, math.nan, 1),
        (0, 0, math.inf, 1),
        ("bad", 0, 1, 1),
    ],
)
def test_invalid_bounds(bounds):
    with pytest.raises(ValueError):
        area_from_bounds(bounds)


def test_bounds_resolve_without_boundary_lookup(tmp_path, monkeypatch):
    import waterlagen.areas as areas

    def unexpected(*args, **kwargs):
        pytest.fail("Boundary lookup for bbox")

    monkeypatch.setattr(areas, "ensure_land_boundary", unexpected)
    monkeypatch.setattr(areas, "download_waterschapsgrenzen", unexpected)
    store = DataStore(data_dir=tmp_path, _env_file=None)
    area = area_from_bounds((184285, 392054, 185285, 393054))
    assert resolve_area(area, store, SourcePreparation(offline=True)) == area
    for name in ("../outside", "a/b", "C:run", "0_0_1_1"):
        with pytest.raises(ValueError):
            area_name(ProductionArea(name, area.geometry, area.crs))
    with pytest.raises(ValueError, match="CRS"):
        resolve_area(
            ProductionArea(area.value, area.geometry, "EPSG:4326"),
            store,
            SourcePreparation(offline=True),
        )


def test_issue63_selects_complete_core_without_edge_only_neighbour():
    area = area_from_bounds((184285, 392054, 185285, 393054))
    grid = gpd.GeoDataFrame(
        {
            "tile_id": ["core", "east"],
            "xmin": [180000, 190000],
            "ymin": [390000, 390000],
        },
        geometry=[
            box(180000, 390000, 190000, 400000),
            box(190000, 390000, 200000, 400000),
        ],
        crs=28992,
    )
    selected = select_area_tiles(grid, area)
    assert selected.tile_id.tolist() == ["core"]
    assert selected.geometry.iloc[0].equals(grid.geometry.iloc[0])
    edge = area_from_bounds((180000, 390000, 190000, 400000))
    assert select_area_tiles(grid, edge).tile_id.tolist() == ["core"]
