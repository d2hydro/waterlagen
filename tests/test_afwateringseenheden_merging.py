from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon, box

from waterlagen.afwateringseenheden import SubcatchmentResult
from waterlagen.afwateringseenheden import tiles as tiles_module
from waterlagen.raster.tiles import Tile
from waterlagen.settings import settings


def test_fill_gap_ignores_linear_remnants() -> None:
    """Line remnants have no area and cannot be used as a GeoPandas clip mask."""
    additions, remaining = tiles_module._fill_gap(LineString([(0, 0), (1, 1)]), [])

    assert additions == []
    assert remaining.is_empty


@pytest.mark.parametrize("first_donor_width", [1, 2])
def test_fill_gap_removes_linear_remnants_between_donors(
    first_donor_width: int,
) -> None:
    # The spike survives subtraction as a line, alone or beside a polygon.
    gap = Polygon([(0, 0), (2, 0), (2, 2), (0, 2), (0, 0), (-1, 0), (0, 0)])
    donors = []
    for tile_id, polygon in [
        ("a", box(0, 0, first_donor_width, 2)),
        ("b", box(1, 0, 2, 2)),
    ]:
        subcatchments = gpd.GeoDataFrame(
            {"segment_fid": [1], "segment_id": ["segment"]},
            geometry=[polygon],
            crs=settings.crs,
        )
        donors.append(tiles_module._GapDonor(tile_id, box(-2, -2, 4, 4), subcatchments))

    additions, remaining = tiles_module._fill_gap(gap, donors)

    assert remaining.is_empty
    assert len(additions) == 3 - first_donor_width
    assigned = gpd.GeoSeries(
        [frame.geometry.union_all() for frame in additions], crs=settings.crs
    )
    assert assigned.union_all().equals(box(0, 0, 2, 2))
    assert assigned.area.sum() == 4
    assert additions[0].bron_tegel.tolist() == ["a"]


def test_gap_filling_uses_safe_neighbour_and_preserves_existing_assignment(
    tmp_path: Path,
) -> None:
    west = Tile("west", 0, 0, 0, 0, 10, 10)
    east = Tile("east", 1, 0, 10, 0, 20, 10)
    existing = box(10, 2, 10.25, 8)
    west_polygons = gpd.GeoDataFrame(
        {"segment_fid": [1, 2], "segment_id": ["safe", "boundary"]},
        # Segment 1 is usable; segment 2 touches the west tile's outer edge.
        geometry=[box(8, 2, 12, 8), box(8, 8, 15, 9)],
        crs=settings.crs,
    )
    east_polygons = gpd.GeoDataFrame(
        {"segment_fid": [3], "segment_id": ["existing"]},
        geometry=[existing],
        crs=settings.crs,
    )
    tile_results = []
    for tile, polygons in [(west, west_polygons), (east, east_polygons)]:
        usable, boundary_issue = tiles_module._usable_subcatchments_for_tile(
            polygons, tile=tile, tile_buffer_m=5, resolution_m=1
        )
        folder = tmp_path / tile.tile_id
        tile_results.append(
            tiles_module.AfwateringseenhedenTileResult(
                tile=tile,
                output_dir=folder,
                rasters=None,
                subcatchments=SubcatchmentResult(
                    folder / "ldd.tif",
                    folder / "subcatchments.tif",
                    folder / "afwateringseenheden.gpkg",
                    polygons,
                ),
                usable_subcatchments=usable,
                calculation_buffer_m=5,
                has_boundary_issue=boundary_issue,
            )
        )

    domain = box(0, 0, 20, 10)
    original = tiles_module._merge_subcatchments(
        [result.usable_subcatchments for result in tile_results], gebied=domain
    )
    filled = tiles_module._fill_gaps_from_neighbours(
        original, tile_results=tile_results, gebied=domain, resolution_m=1
    )
    merged = tiles_module._merge_subcatchments(
        [original, filled.additions], gebied=domain
    ).set_index("segment_id")

    assert filled.additions.segment_id.tolist() == ["safe"]
    assert filled.additions.bron_tegel.tolist() == ["west"]
    assert filled.additions.geometry.union_all().equals(box(10.25, 2, 12, 8))
    assert merged.loc["existing"].geometry.equals(existing)
    assert merged.loc["safe"].geometry.equals(box(8, 2, 12, 8).difference(existing))
    assert "boundary" not in merged.index
    assert merged.geometry.union_all().intersection(box(10, 8, 12, 9)).area == 0
    assert merged.area.sum() == merged.geometry.union_all().area
