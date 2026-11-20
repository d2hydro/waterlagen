"""Gebiedsbestanden behouden hun vorm, gaten, CRS en herkomstidentiteit."""

import geopandas as gpd
import pytest
from shapely.geometry import MultiPolygon, Point, Polygon, box

from waterlagen import areas


@pytest.mark.parametrize("suffix", [".gpkg", ".geojson"])
def test_polygon_selection_keeps_holes_and_separate_parts(tmp_path, suffix):
    path = tmp_path / f"gebied{suffix}"
    donut = Polygon(box(0, 0, 3, 3).exterior.coords, [box(1, 1, 2, 2).exterior.coords])
    shape = MultiPolygon([donut, box(5, 0, 6, 1)])
    gpd.GeoDataFrame(geometry=[shape], crs=28992).to_file(path)
    area = areas.area_from_file(path)
    assert area.geometry.equals(shape)
    assert areas.area_name(area).startswith("polygoon_")
    assert areas.resolve_area(area, None, None).geometry.equals(shape)
    grid = gpd.GeoDataFrame(
        {
            "tile_id": ["rand", "gat", "tussen", "los"],
            "xmin": [0, 1, 4, 5],
            "ymin": [0, 1, 0, 0],
        },
        geometry=[box(0, 0, 1, 1), box(1, 1, 2, 2), box(4, 0, 5, 1), box(5, 0, 6, 1)],
        crs=28992,
    )
    selected = areas.select_area_tiles(grid, area)
    assert set(selected.tile_id) == {"rand", "los"}
    assert selected.geometry.area.tolist() == [1, 1]


def test_multiple_layers_require_explicit_choice(tmp_path):
    path = tmp_path / "gebieden.gpkg"
    for name, shape in [("west", box(0, 0, 1, 1)), ("oost", box(2, 0, 3, 1))]:
        gpd.GeoDataFrame(geometry=[shape], crs=28992).to_file(path, layer=name)
    assert areas.area_file_layers(path) == ["west", "oost"]
    with pytest.raises(ValueError, match="meerdere polygoonlagen"):
        areas.area_from_file(path)
    assert areas.area_from_file(path, layer="oost").geometry.equals(box(2, 0, 3, 1))
    with pytest.raises(ValueError, match="niet gevonden"):
        areas.area_from_file(path, layer="ontbreekt")


def test_all_features_form_one_area_and_geometry_change_changes_identity(tmp_path):
    path = tmp_path / "gebied.gpkg"
    first = box(0, 0, 1, 1)
    second = box(2, 0, 3, 1)
    gpd.GeoDataFrame(geometry=[first, second], crs=28992).to_file(path)
    before = areas.area_from_file(path)
    gpd.GeoDataFrame(geometry=[second, first.reverse()], crs=28992).to_file(path)
    assert areas.area_from_file(path).identity == before.identity
    gpd.GeoDataFrame(geometry=[first], crs=28992).to_file(path)
    after = areas.area_from_file(path)
    assert after.value != before.value
    assert after.identity != before.identity


def test_geographic_file_is_transformed_to_project_crs(tmp_path):
    path = tmp_path / "gebied.geojson"
    original = gpd.GeoDataFrame(
        geometry=[box(110000, 515000, 111000, 516000)], crs=28992
    )
    original.to_crs(4326).to_file(path)
    area = areas.area_from_file(path)
    assert area.crs == "EPSG:28992"
    assert area.geometry.hausdorff_distance(original.geometry.iloc[0]) < 0.01


@pytest.mark.parametrize(
    "shape", [Point(0, 0), Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])]
)
def test_points_and_invalid_polygons_are_rejected(tmp_path, shape):
    path = tmp_path / "gebied.gpkg"
    gpd.GeoDataFrame(geometry=[shape], crs=28992).to_file(path)
    with pytest.raises(ValueError, match="polygoonlaag|geldige polygonen"):
        areas.area_from_file(path)


@pytest.mark.parametrize("missing", ["crs", "null", "empty"])
def test_missing_crs_or_geometry_is_rejected(tmp_path, monkeypatch, missing):
    path = tmp_path / "gebied.gpkg"
    frame = gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs=28992)
    frame.to_file(path)
    if missing == "crs":
        frame = frame.set_crs(None, allow_override=True)
    else:
        frame.geometry = [None if missing == "null" else Polygon()]
    monkeypatch.setattr(areas, "read_file", lambda *args, **kwargs: frame)
    with pytest.raises(ValueError):
        areas.area_from_file(path)


def test_unreadable_or_missing_files_raise_clear_errors(tmp_path):
    path = tmp_path / "gebied.gpkg"
    with pytest.raises(ValueError, match="bestaat niet"):
        areas.area_from_file(path)
    path.write_text("geen GeoPackage")
    with pytest.raises(ValueError, match="niet lezen"):
        areas.area_from_file(path)
