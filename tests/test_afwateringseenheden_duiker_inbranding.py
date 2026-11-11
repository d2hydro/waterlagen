"""Actual per-object burn effects, including overlaps and missing coverage."""

import json

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from shapely.geometry import box
from test_afwateringseenheden_waternet import cell, grid, line, optional, sources

from waterlagen.afwateringseenheden import prepare_watersysteem_rasters
from waterlagen.afwateringseenheden._duiker_inbranding import (
    TRACE_FILENAME,
    _read_burn_counts,
)
from waterlagen.afwateringseenheden._signaalnetwerk import read_used_network
from waterlagen.afwateringseenheden.config import BrandlagenConfig
from waterlagen.afwateringseenheden.waternet import prepare_waternet
from waterlagen.settings import settings


def calculate(tmp_path, data, *, extra=None, depth=10, boundary=None):
    network = tmp_path / "watersysteem.gpkg"
    data.primary.to_file(network, layer="hydroobject_primair")
    data.secondary.to_file(network, layer="hydroobject_secundair")
    targets = data.primary.copy()
    targets["segment_key"] = [f"primary-{i}" for i in range(len(targets))]
    targets.to_file(network, layer="hydroobject_segment")
    ahn = tmp_path / "ahn.tif"
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
    ) as output:
        output.write(np.full((20, 20), 100, dtype="float32"), 1)
    prepare_waternet(
        data,
        optional() if extra is None else extra,
        [grid()],
        network,
        BrandlagenConfig(geisoleerde_branddiepte_m=depth),
    )
    boundary_path = None
    if boundary is not None:
        boundary_path = tmp_path / "boundary.gpkg"
        gpd.GeoDataFrame(geometry=[boundary], crs=settings.crs).to_file(
            boundary_path, layer="landgebied"
        )
    options = {
        "burn_depth_m": 10,
        "ahn_vrt_path": ahn,
        "watersysteem_path": network,
        "output_dir": tmp_path / "berekening" / "tegels" / "test",
        "landsgrens_path": boundary_path,
    }
    result = prepare_watersysteem_rasters(box(0, 0, 40, 40), **options)
    return result, options


def connected(culverts=None):
    return sources(
        primary=[line((37, 1), (37, 39))],
        secondary=[line((1, 21), (11, 21)), line((21, 21), (37, 21))],
        culverts=culverts or [line((11, 21), (21, 21))],
    )


def test_same_source_overlap_records_only_actual_winner(tmp_path):
    geometry = line((11, 21), (21, 21))
    result, _ = calculate(tmp_path, connected([geometry, geometry]))
    counts, complete = _read_burn_counts([result.dem_path])
    assert complete
    assert counts["hydamo-0"]["toegepast"] == 0
    assert counts["hydamo-1"]["toegepast"] > 0
    with rasterio.open(result.dem_path) as source:
        assert source.read(1)[cell(grid(), 15, 21)] == 90


def test_new_run_supplies_actual_burn_evidence_to_signal_map(tmp_path):
    """The producer, not a manually supplied audit fixture, enables the 2 m check."""
    data = connected()
    calculate(tmp_path, data)
    signals = data.culverts[["geometry"]].copy()
    network = read_used_network(tmp_path, data.primary, signals)
    assert any(
        geometry.equals(signals.geometry.iloc[0]) for geometry in network.geometry
    )


def test_missing_dem_is_distinct_from_displaced_burning(tmp_path):
    result, _ = calculate(tmp_path, connected(), boundary=box(30, 0, 40, 40))
    counts, complete = _read_burn_counts([result.dem_path])
    assert complete
    assert counts["hydamo-0"]["winnend"] > 0
    assert counts["hydamo-0"]["geldige_dem"] == 0
    assert counts["hydamo-0"]["toegepast"] == 0


def test_zero_depth_is_not_actual_burning(tmp_path):
    data = sources(
        tertiary=[line((1, 21), (11, 21)), line((21, 21), (37, 21))],
        culverts=[line((11, 21), (21, 21))],
    )
    result, _ = calculate(tmp_path, data, depth=0)
    counts, complete = _read_burn_counts([result.dem_path])
    assert complete
    assert counts["hydamo-0"]["geldige_dem"] > 0
    assert counts["hydamo-0"]["toegepast"] == 0


def test_optional_depth_priority_keeps_matching_object_identity(tmp_path):
    geometry = line((11, 21), (21, 21))
    extra = optional([geometry, geometry], ["duiker", "duiker"], ["bgt", "bgt"])
    # Both registrations belong to one source layer; high priority is first.
    extra["broncode"] = 3
    extra["brandwaarde"] = [-7.0, -2.0]
    extra["prioriteit"] = [5, 1]
    data = sources(tertiary=[line((1, 21), (11, 21)), line((21, 21), (37, 21))])
    result, _ = calculate(tmp_path, data, extra=extra)
    counts, complete = _read_burn_counts([result.dem_path])
    assert complete
    assert counts["optional.gpkg|objects|0"]["toegepast"] > 0
    assert counts["optional.gpkg|objects|1"]["toegepast"] == 0
    with rasterio.open(result.dem_path) as source:
        assert source.read(1)[cell(grid(), 15, 21)] == 93


@pytest.mark.parametrize("damage", ["missing", "stale", "invalid"])
def test_missing_or_stale_trace_is_unknown_and_rebuilt_on_resume(tmp_path, damage):
    result, options = calculate(tmp_path, connected())
    trace = result.dem_path.with_name(TRACE_FILENAME)
    if damage == "missing":
        trace.unlink()
    elif damage == "stale":
        data = json.loads(trace.read_text())
        data["burn_signature"] = "wrong"
        trace.write_text(json.dumps(data))
    else:
        trace.write_text("not json")
    counts, complete = _read_burn_counts([result.dem_path])
    assert not complete
    assert not counts
    prepare_watersysteem_rasters(box(0, 0, 40, 40), **options)
    counts, complete = _read_burn_counts([result.dem_path])
    assert complete
    assert counts["hydamo-0"]["toegepast"] > 0
