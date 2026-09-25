from xml.etree import ElementTree as ET

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from shapely.geometry import box

from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik import (
    FunctioneelLandgebruikSources,
    bouw_functioneel_landgebruik,
)
from waterlagen.functioneel_landgebruik import landgebruik_berekenen as build_mod
from waterlagen.raster.config import RasterOutputConfig


def _patch_sources(monkeypatch, prepared_sources=()):
    monkeypatch.setattr(build_mod, "_download_missing_sources", lambda *args: None)
    monkeypatch.setattr(build_mod, "_validate_sources_exist", lambda sources: None)
    monkeypatch.setattr(build_mod, "_read_dike_area", lambda *args: object())
    monkeypatch.setattr(
        build_mod,
        "_prepare_priority_sources",
        lambda *args, **kwargs: list(prepared_sources),
    )


def test_output_crs_must_match_project(tmp_path):
    target = tmp_path / "result.tif"
    with pytest.raises(ValueError, match="Raster-CRS"):
        bouw_functioneel_landgebruik(target, bounds=(0, 0, 1, 1), crs="EPSG:4326")
    assert not target.exists()


def test_dike_crs_must_match_project(tmp_path):
    path = tmp_path / "dikes.gpkg"
    gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs=4326).to_file(
        path, layer="dijkring_v_2012", driver="GPKG"
    )
    sources = FunctioneelLandgebruikSources(dijkringen_gpkg=path)
    with pytest.raises(ValueError, match="CRS van dijkringen"):
        build_mod._read_dike_area(sources, build_mod.FunctioneelLandgebruikLayers())


def test_sources_are_derived_from_injected_datastore(tmp_path):
    data_store = DataStore(data_dir=tmp_path / "data")

    sources = FunctioneelLandgebruikSources.from_datastore(data_store)

    assert sources.bgt_gpkg == data_store.bgt_dir / "bgt.gpkg"
    assert sources.bag_gpkg == data_store.bag_dir / "bag-light.gpkg"
    assert sources.brp_gpkg == (
        data_store.brp_dir / "brpgewaspercelen_definitief_2025.gpkg"
    )
    assert sources.top10nl_gpkg == data_store.top10nl_dir / "top10nl_Compleet.gpkg"
    assert sources.dijkringen_gpkg == (
        data_store.dijkringen_dir / "dijkringen_historie_2012.gpkg"
    )


def test_build_allocates_one_full_tile_raster_and_reuses_it(tmp_path, monkeypatch):
    _patch_sources(monkeypatch, prepared_sources=["a", "b", "c"])
    full_calls = []
    raster_ids = []
    original_full = np.full

    def fake_full(shape, fill_value, dtype):
        full_calls.append((shape, fill_value, dtype))
        return original_full(shape, fill_value, dtype=dtype)

    def fake_rasterize(raster, data, transform):
        raster_ids.append(id(raster))
        raster[:, :] = len(raster_ids)
        return raster

    monkeypatch.setattr(build_mod.np, "full", fake_full)
    monkeypatch.setattr(build_mod, "rasterize_features", fake_rasterize)

    target = tmp_path / "landgebruik.tif"
    bouw_functioneel_landgebruik(
        target_path=target,
        bounds=(0, 0, 16, 16),
        resolution_m=1,
        output_config=RasterOutputConfig(block_size=16, overview_factors=(2,)),
        download_missing=False,
    )

    assert full_calls == [((16, 16), 0, np.uint8)]
    assert len(set(raster_ids)) == 1
    palette = ET.parse(target.with_suffix(".qml")).findall(
        "./pipe/rasterrenderer/colorPalette/paletteEntry"
    )
    labels = {int(entry.attrib["value"]): entry.attrib for entry in palette}
    assert "Water (binnendijks)" in labels[100]["label"]
    assert "Water (buitendijks)" in labels[228]["label"]
    assert "Overig gras/natuur" in labels[182]["label"]
    assert "Agrarisch" not in labels[182]["label"]
    assert labels[0]["alpha"] == "0"
    with rasterio.open(target) as src:
        assert src.read(1).min() == 3
        assert src.read(1).max() == 3


def test_build_default_output_is_tiled_512_with_mode_overviews(tmp_path, monkeypatch):
    _patch_sources(monkeypatch)

    target = tmp_path / "landgebruik_default.tif"
    bouw_functioneel_landgebruik(
        target_path=target,
        bounds=(0, 0, 1024, 1024),
        resolution_m=1,
        download_missing=False,
    )

    with rasterio.open(target) as src:
        assert src.profile["tiled"] is True
        assert src.block_shapes == [(512, 512)]
        assert src.overviews(1) == [4, 8, 16, 32, 64, 128, 256]
        assert src.tags(ns="rio_overview")["resampling"] == "mode"
        assert src.nodata == 0
        assert src.descriptions == ("Landgebruik",)


def test_build_accepts_custom_output_config(tmp_path, monkeypatch):
    _patch_sources(monkeypatch)

    target = tmp_path / "landgebruik_custom.tif"
    bouw_functioneel_landgebruik(
        target_path=target,
        bounds=(0, 0, 64, 64),
        resolution_m=1,
        output_config=RasterOutputConfig(block_size=16, overview_factors=(2, 4)),
        download_missing=False,
    )

    with rasterio.open(target) as src:
        assert src.block_shapes == [(16, 16)]
        assert src.overviews(1) == [2, 4]
