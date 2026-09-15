from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from geopandas.testing import assert_geodataframe_equal
from rasterio.transform import from_origin
from shapely.geometry import LineString, box

from waterlagen.afwateringseenheden import calculate_afwateringseenheden_tiles
from waterlagen.settings import settings


@pytest.fixture
def sources(tmp_path: Path) -> tuple[Path, Path]:
    dem_path = tmp_path / "dem.tif"
    dem = np.full((24, 32), 1000, dtype=np.int16)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        width=32,
        height=24,
        count=1,
        dtype="int16",
        nodata=-32768,
        crs=settings.crs,
        transform=from_origin(0, 48, 2, 2),
    ) as dataset:
        dataset.scales = (0.01,)
        dataset.write(dem, 1)
    watersysteem_path = tmp_path / "watersysteem.gpkg"
    primary = gpd.GeoDataFrame(
        {"segment_id": ["first", "second", "third"]},
        geometry=[LineString([(x, 0), (x, 48)]) for x in (10, 26, 42)],
        crs=settings.crs,
    )
    for layer in ("hydroobject_primair", "hydroobject_segment"):
        primary.to_file(watersysteem_path, layer=layer, driver="GPKG", index=False)
    secondary = primary.iloc[:0]
    secondary.to_file(
        watersysteem_path, layer="hydroobject_secundair", driver="GPKG", index=False
    )
    return dem_path, watersysteem_path


def test_six_workers_match_serial_and_reuse_output(
    sources: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    pytest.importorskip("pcraster")
    dem_path, watersysteem_path = sources
    input_bytes = [path.read_bytes() for path in sources]
    options = {
        "burn_depth_m": 1,
        "ahn_vrt_path": dem_path,
        "watersysteem_path": watersysteem_path,
        "tile_size_m": 16,
        "tile_buffer_m": 4,
        "origin_x": 8,
        "origin_y": 8,
        "resolution_m": 2,
        "random_seed": 12345,
    }
    serial = calculate_afwateringseenheden_tiles(
        box(8, 8, 56, 40),
        **options,
        workers=1,
        output_dir=tmp_path / "serial",
        merged_output_path=tmp_path / "serial.gpkg",
    )
    parallel = calculate_afwateringseenheden_tiles(
        box(8, 8, 56, 40),
        **options,
        workers=6,
        output_dir=tmp_path / "parallel",
        merged_output_path=tmp_path / "parallel.gpkg",
    )
    assert len(parallel.tile_results) == 6
    assert [item.tile.tile_id for item in serial.tile_results] == [
        item.tile.tile_id for item in parallel.tile_results
    ]
    assert serial.boundary_issue_tile_ids == parallel.boundary_issue_tile_ids
    assert serial.skipped_tile_ids == parallel.skipped_tile_ids
    assert_geodataframe_equal(
        serial.merged_subcatchments, parallel.merged_subcatchments
    )
    versions = {}
    for first, second in zip(serial.tile_results, parallel.tile_results, strict=True):
        assert second.subcatchments is not None
        assert (second.output_dir / "workflow.log").exists()
        for filename in (
            "dem_2m.tif",
            "hydroobject_segment.tif",
            "ldd.tif",
            "subcatchments.tif",
        ):
            with (
                rasterio.open(first.output_dir / filename) as a,
                rasterio.open(second.output_dir / filename) as b,
            ):
                assert a.transform == b.transform
                assert a.crs == b.crs
                assert a.nodata == b.nodata
                np.testing.assert_array_equal(a.read(1), b.read(1))
            path = second.output_dir / filename
            versions[path] = path.stat().st_mtime_ns
        assert_geodataframe_equal(
            first.usable_subcatchments, second.usable_subcatchments
        )
    reused = calculate_afwateringseenheden_tiles(
        box(8, 8, 56, 40),
        **options,
        workers=6,
        output_dir=tmp_path / "parallel",
    )
    assert all(result.subcatchments is None for result in reused.tile_results)
    for attribute in ("merged_subcatchments", "gap_additions", "remaining_gaps"):
        assert_geodataframe_equal(
            getattr(serial, attribute), getattr(parallel, attribute)
        )
        assert_geodataframe_equal(
            getattr(parallel, attribute), getattr(reused, attribute)
        )
    assert all(path.stat().st_mtime_ns == version for path, version in versions.items())
    assert [path.read_bytes() for path in sources] == input_bytes
