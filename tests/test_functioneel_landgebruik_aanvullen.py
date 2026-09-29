import json

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from shapely.geometry import box

from waterlagen.functioneel_landgebruik import landgebruik_berekenen as build
from waterlagen.functioneel_landgebruik.aanvullen import (
    DONOR_ALLOWED,
    SOURCE_LAYERS,
    _fill_gaps,
    _source_path,
    _validate_outputs,
)
from waterlagen.raster.config import RasterOutputConfig


def fill(values, sources, radius=1.0, land=None):
    return _fill_gaps(
        values,
        sources,
        np.ones_like(values, dtype=bool) if land is None else land,
        radius_m=radius,
        pixel_width=0.5,
        pixel_height=0.5,
    )


@pytest.mark.parametrize("source_id", list(SOURCE_LAYERS))
def test_source_mapping_controls_donors(source_id):
    values = np.array([[78, 0, 0, 0]], dtype="uint8")
    sources = np.array([[source_id, 0, 0, 0]], dtype="uint8")
    filled = fill(values, sources)
    expected = 2 if DONOR_ALLOWED[source_id] else 0
    assert filled == expected
    assert values.tolist() == ([[78, 78, 78, 0]] if expected else [[78, 0, 0, 0]])
    assert sources[0, 1] == (source_id if expected else 0)


def test_protected_nodata_existing_values_and_land_mask():
    values = np.array([[78, 0, 0, 52]], dtype="uint8")
    sources = np.array([[2, 10, 0, 7]], dtype="uint8")
    land = np.array([[True, True, False, True]])
    assert fill(values, sources, land=land) == 0
    assert values.tolist() == [[78, 0, 0, 52]]
    assert sources.tolist() == [[2, 10, 0, 7]]


def test_nearest_eligible_donor_and_tie_order():
    values = np.array([[78, 0, 100]], dtype="uint8")
    sources = np.array([[2, 0, 12]], dtype="uint8")
    fill(values, sources)
    assert values[0, 1] == 78  # Equal distance: western donor.
    assert sources[0, 1] == 2
    values = np.array([[78, 0, 52, 0]], dtype="uint8")
    sources = np.array([[2, 0, 7, 0]], dtype="uint8")
    fill(values, sources, radius=2)
    assert values.tolist() == [[78, 78, 52, 78]]  # Excluded closer donor ignored.


def test_diagonal_distance_and_no_cascading():
    values = np.zeros((4, 4), dtype="uint8")
    sources = np.zeros_like(values)
    values[0, 0], sources[0, 0] = 78, 2
    fill(values, sources)
    assert values[1, 1] == 78
    assert values[2, 0] == 78  # Exactly one metre.
    assert values[2, 1] == 0  # More than one metre.
    assert values[3, 0] == 0  # No chaining through newly filled pixels.


@pytest.mark.parametrize("radius", [-1, float("nan"), float("inf")])
def test_invalid_radius(radius):
    with pytest.raises(ValueError, match="gap_fill_distance_m"):
        fill(np.zeros((1, 1)), np.zeros((1, 1)), radius)


def test_disabled_and_no_donors():
    values = np.array([[78, 0]], dtype="uint8")
    sources = np.array([[2, 0]], dtype="uint8")
    assert fill(values, sources, radius=0) == 0
    assert values.tolist() == [[78, 0]]
    assert fill(np.zeros_like(values), np.zeros_like(sources)) == 0


@pytest.fixture
def synthetic_sources(monkeypatch):
    monkeypatch.setattr(build, "_validate_sources_exist", lambda *args: None)
    monkeypatch.setattr(
        build, "_read_buitendijks_area", lambda *args: box(100, 100, 101, 101)
    )
    monkeypatch.setattr(
        build,
        "read_landsgrens",
        lambda: gpd.GeoDataFrame(geometry=[box(0, 0, 8, 4)], crs=28992),
    )
    frames = [
        gpd.GeoDataFrame(
            {"code": [78], "source_code": [2]},
            geometry=[box(3.6, 1.1, 3.9, 1.4)],
            crs=28992,
        ),
        gpd.GeoDataFrame(
            {"code": [0], "source_code": [10]},
            geometry=[box(4.1, 1.1, 4.4, 1.4)],
            crs=28992,
        ),
    ]
    monkeypatch.setattr(
        build, "_prepare_priority_sources", lambda *args, **kwargs: frames
    )
    return frames


def make_tile(path, bounds, **kwargs):
    return build.bouw_functioneel_landgebruik(
        path,
        bounds=bounds,
        resolution_m=0.5,
        download_missing=False,
        output_config=RasterOutputConfig(block_size=16, overview_factors=()),
        **kwargs,
    )


def read(path):
    with rasterio.open(path) as src:
        return src.read(1)


def test_tiles_match_whole_extent_and_provenance(tmp_path, synthetic_sources):
    whole = make_tile(tmp_path / "whole.tif", (0, 0, 8, 4))
    left = make_tile(tmp_path / "left.tif", (0, 0, 4, 4))
    right = make_tile(tmp_path / "right.tif", (4, 0, 8, 4))
    assert np.array_equal(read(whole), np.hstack([read(left), read(right)]))
    assert np.array_equal(
        read(_source_path(whole)),
        np.hstack([read(_source_path(left)), read(_source_path(right))]),
    )
    assert read(right).any()  # Donor from neighbouring tile used.
    assert np.any((read(right) == 0) & (read(_source_path(right)) == 10))
    with rasterio.open(_source_path(right)) as src:
        assert json.loads(src.tags()["source_layers"])["10"] == "BAG:pand"
    _validate_outputs(whole, 1)
    with pytest.raises(ValueError, match="overwrite=True"):
        _validate_outputs(whole, 2)
    _source_path(whole).unlink()
    with pytest.raises(FileNotFoundError, match="overwrite=True"):
        _validate_outputs(whole, 1)


def test_later_source_overwrites_donor_provenance(tmp_path, synthetic_sources):
    geometry = synthetic_sources[0].geometry.iloc[0]
    synthetic_sources.append(
        gpd.GeoDataFrame(
            {"code": [50], "source_code": [7]}, geometry=[geometry], crs=28992
        )
    )
    result = make_tile(tmp_path / "excluded.tif", (0, 0, 8, 4))
    values = read(result)
    source = read(_source_path(result))
    assert np.count_nonzero(values) == 1
    assert source[values != 0].tolist() == [7]


def test_mismatched_pair_is_not_reused(tmp_path, synthetic_sources):
    output = make_tile(tmp_path / "pair.tif", (0, 0, 8, 4))
    with rasterio.open(_source_path(output), "r+") as source:
        source.update_tags(output_pair="different")
    with pytest.raises(ValueError, match="Output pair differs"):
        make_tile(output, (0, 0, 8, 4), overwrite=False)


def test_filling_stays_within_landgebied(tmp_path, synthetic_sources, monkeypatch):
    monkeypatch.setattr(
        build,
        "read_landsgrens",
        lambda: gpd.GeoDataFrame(geometry=[box(0, 0, 4, 4)], crs=28992),
    )
    output = make_tile(tmp_path / "land.tif", (0, 0, 8, 4))
    assert not read(output)[:, 8:].any()


def test_two_metre_gap_filled_from_both_sides():
    values = np.array([[78, 0, 0, 0, 0, 100]], dtype="uint8")
    sources = np.array([[2, 0, 0, 0, 0, 12]], dtype="uint8")
    assert fill(values, sources) == 4
    assert values.tolist() == [[78, 78, 78, 100, 100, 100]]
    assert sources.tolist() == [[2, 2, 2, 12, 12, 12]]
