from dataclasses import replace

import geopandas as gpd
import numpy as np
import pytest
from rasterio.features import rasterize
from shapely.affinity import translate
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, box

from waterlagen.afwateringseenheden import (
    Brandlaag,
    BrandlagenConfig,
    calculate_afwateringseenheden_tiles,
    prepare_watersysteem_rasters,
    read_brandlagen,
    read_brandlagen_config,
)
from waterlagen.afwateringseenheden import brandlagen as module
from waterlagen.afwateringseenheden.raster import _grid_for_square
from waterlagen.settings import settings


@pytest.mark.parametrize("origin", [(0, 0), (155000.13, 460000.71)])
def test_local_conflict_check_matches_full_buffered_rasters(tmp_path, origin):
    geometries = [
        LineString([(2.2, 2.2), (9.7, 8.2)]),
        LineString([(2.3, 2.3), (9.8, 8.3)]),
        LineString([(-8, 5.1), (8, 6.1)]),
        box(5, 4, 6, 7),
        LineString([(14, 15), (15, 15)]),
        box(17, 17, 18, 18),
    ]
    shifted = [translate(g, xoff=origin[0], yoff=origin[1]) for g in geometries]
    source = write_layer(
        tmp_path / "burn.gpkg",
        shifted,
        brandwaarde=[-1, 2, 1, -1, -1, 1],
        prioriteit=[0] * len(shifted),
    )
    features = read_brandlagen(BrandlagenConfig((Brandlaag(source, "objects"),)))
    grids = [
        _grid_for_square(translate(box(x, 0, x + 20, 20), *origin), resolution_m=2)
        for x in (0, 8)
    ]
    expected = set()
    for grid in grids:
        masks = [
            rasterize(
                [(row.geometry, 1)],
                out_shape=(grid.height, grid.width),
                transform=grid.transform,
                dtype="uint8",
                all_touched=False,
            ).astype(bool)
            for row in features.itertuples()
        ]
        for i, row in enumerate(features.itertuples()):
            for j, other in enumerate(features.itertuples()):
                if row.brandwaarde * other.brandwaarde < 0 and np.any(
                    masks[i] & masks[j]
                ):
                    expected.add(row.bron_fid)
    errors = module._conflict_errors(features, grids)
    assert expected
    assert len(errors) == len(expected)
    for fid in features.bron_fid:
        assert any(f"FID {fid}:" in error for error in errors) == (fid in expected)


def write_layer(path, geometries, *, layer="objects", crs=None, **attributes):
    gpd.GeoDataFrame(attributes, geometry=geometries, crs=crs or settings.crs).to_file(
        path, layer=layer, index=False
    )
    return path


def test_object_layer_global_defaults_and_zero(tmp_path):
    path = write_layer(
        tmp_path / "input.gpkg",
        [box(i, 0, i + 1, 1) for i in range(3)],
        brandwaarde=[0, None, -4],
        prioriteit=[0, None, 2],
    )
    write_layer(path, [LineString([(0, 4), (8, 4)])], layer="lines")
    config = BrandlagenConfig(
        (Brandlaag(path, "objects", brandwaarde=-3), Brandlaag(path, "lines")),
        brandwaarde=2,
        prioriteit=1,
    )
    features = read_brandlagen(config)
    assert features.brandwaarde.tolist() == [0, 2, -3, -4]
    assert features.prioriteit.tolist() == [0, 1, 1, 2]
    assert features.bron_fid.tolist() == [1, 1, 2, 3]
    assert set(features.bronbestand) == {str(path.resolve())}
    assert features.crs == settings.crs


@pytest.mark.parametrize(
    "geometry",
    [
        LineString([(155000, 460000), (155010, 460010)]),
        MultiLineString([[(155000, 460000), (155010, 460010)]]),
        box(155000, 460000, 155010, 460010),
        MultiPolygon([box(155000, 460000, 155010, 460010)]),
    ],
)
def test_selection_uses_source_crs_and_preserves_original_fid(tmp_path, geometry):
    features = gpd.GeoDataFrame(
        {"brandwaarde": [-1, -2], "prioriteit": [1, 1]},
        geometry=[box(140000, 450000, 140010, 450010), geometry],
        crs=settings.crs,
    ).to_crs(4326)
    path = tmp_path / "geographic.gpkg"
    features.to_file(path, layer="objects")
    result = read_brandlagen(
        BrandlagenConfig((Brandlaag(path, "objects"),)),
        spatial_selection=box(154999, 459999, 155011, 460011),
    )
    assert result.bron_fid.tolist() == [2]
    assert result.brandwaarde.tolist() == [-2]
    assert result.geometry.iloc[0].hausdorff_distance(geometry) < 0.01


def test_collects_source_geometry_and_attribute_errors(tmp_path):
    path = write_layer(
        tmp_path / "bad.gpkg",
        [box(0, 0, 2, 2), box(2, 0, 4, 2)],
        brandwaarde=[None, float("inf")],
        prioriteit=[1.5, 1],
    )
    write_layer(path, [Point(1, 1)], layer="points", brandwaarde=[1], prioriteit=[1])
    config = BrandlagenConfig(
        (
            Brandlaag(path, "objects"),
            Brandlaag(path, "points"),
            Brandlaag(tmp_path / "missing.gpkg", "missing"),
        )
    )
    with pytest.raises(ValueError) as caught:
        read_brandlagen(config)
    message = str(caught.value)
    assert "objects / FID 1: brandwaarde" in message
    assert "objects / FID 1: prioriteit" in message
    assert "objects / FID 2: brandwaarde" in message
    assert "points / FID 1: unsupported geometry" in message
    assert "missing.gpkg / missing" in message


@pytest.mark.parametrize("value", [True, "3", float("inf"), float("nan")])
def test_rejects_invalid_defaults(tmp_path, value):
    with pytest.raises(ValueError):
        Brandlaag(tmp_path / "x.gpkg", "objects", brandwaarde=value)
    with pytest.raises(ValueError):
        BrandlagenConfig(prioriteit=value)


def test_toml_resolves_relative_paths_and_rejects_unknown_keys(tmp_path, monkeypatch):
    folder = tmp_path / "config"
    folder.mkdir()
    path = folder / "burn.toml"
    path.write_text("""[defaults]
brandwaarde = -2.5
prioriteit = 0
[[lagen]]
path = "../source.gpkg"
layer = "roads"
brandwaarde = 3.0
""")
    monkeypatch.chdir(tmp_path)
    config = read_brandlagen_config(path)
    assert config.brandwaarde == -2.5
    assert config.prioriteit == 0
    assert config.lagen == (
        Brandlaag(tmp_path / "source.gpkg", "roads", brandwaarde=3),
    )
    path.write_text('[[lagen]]\npath = "x.gpkg"\nlayer = "roads"\nprio = 1')
    with pytest.raises(ValueError, match="Unknown laag keys: prio"):
        read_brandlagen_config(path)


def test_grid_conflicts_report_all_fids_once_before_any_dem_access(tmp_path):
    # Disjoint lines share raster cells; the third object hides them but must
    # not conceal invalid input. Repeated grids must not duplicate diagnostics.
    path = write_layer(
        tmp_path / "conflict.gpkg",
        [LineString([(x, 0), (x, 8)]) for x in (0.5, 1.5, 1)],
        brandwaarde=[-1, 1, 4],
        prioriteit=[1, 1, 2],
    )
    invalid = write_layer(tmp_path / "invalid.gpkg", [box(0, 0, 2, 2)])
    config = BrandlagenConfig(
        (Brandlaag(path, "objects"), Brandlaag(invalid, "objects"))
    )
    grid = _grid_for_square(box(0, 0, 8, 8), resolution_m=2)
    with pytest.raises(ValueError) as caught:
        module._prepare_brandlagen(config, [grid, grid], tmp_path / "prepared.gpkg")
    message = str(caught.value)
    assert message.count("FID 1: opposite signs") == 1
    assert message.count("FID 2: opposite signs") == 1
    assert "FID 3: opposite signs" not in message
    assert "invalid.gpkg / objects / FID 1: brandwaarde" in message
    assert not (tmp_path / "prepared.gpkg").exists()
    with pytest.raises(ValueError, match="opposite signs"):
        prepare_watersysteem_rasters(
            box(0, 0, 8, 8),
            burn_depth_m=100,
            brandlagen=BrandlagenConfig((Brandlaag(path, "objects"),)),
            ahn_vrt_path=tmp_path / "missing.tif",
            output_dir=tmp_path / "rasters",
        )


def test_tile_preflight_runs_before_workers(tmp_path, monkeypatch):
    path = write_layer(
        tmp_path / "conflicts.gpkg",
        [box(0, 0, 8, 8)] * 2,
        brandwaarde=[-1, 1],
        prioriteit=[1, 1],
    )
    from waterlagen.afwateringseenheden import tiles

    monkeypatch.setattr(
        tiles, "_calculate_tiles_parallel", lambda *a: pytest.fail("workers started")
    )
    with pytest.raises(ValueError, match="opposite signs"):
        calculate_afwateringseenheden_tiles(
            box(0, 0, 8, 8),
            burn_depth_m=1,
            workers=2,
            tile_size_m=8,
            tile_buffer_m=0,
            output_dir=tmp_path / "tiles",
            brandlagen=BrandlagenConfig((Brandlaag(path, "objects"),)),
        )


def test_snapshot_reuse_and_defaults_invalidate_preflight(tmp_path, monkeypatch):
    path = write_layer(tmp_path / "input.gpkg", [box(0, 0, 8, 8)])
    config = BrandlagenConfig(
        (Brandlaag(path, "objects"),), brandwaarde=-1, prioriteit=0
    )
    grid = _grid_for_square(box(0, 0, 8, 8), resolution_m=2)
    target = tmp_path / "output" / "prepared.gpkg"
    prepared = module._prepare_brandlagen(config, [grid], target)
    version = target.stat().st_mtime_ns
    original = module._conflict_errors
    calls = []

    def check(features, grids):
        calls.append(len(features))
        return original(features, grids)

    monkeypatch.setattr(module, "_conflict_errors", check)
    assert module._prepare_brandlagen(config, [grid], target) == prepared
    assert calls == []
    assert target.stat().st_mtime_ns == version
    changed = module._prepare_brandlagen(
        replace(config, brandwaarde=-2), [grid], target
    )
    assert changed.signature != prepared.signature
    assert calls == [1]
    assert np.all(module._optional_burn_values(changed, grid) == -2)


def test_optional_conflict_outside_selected_grid_does_not_fail(tmp_path):
    path = write_layer(
        tmp_path / "input.gpkg",
        [box(20, 20, 30, 30)] * 2,
        brandwaarde=[-1, 1],
        prioriteit=[1, 1],
    )
    config = BrandlagenConfig((Brandlaag(path, "objects"),))
    grid = _grid_for_square(box(0, 0, 8, 8), resolution_m=2)
    prepared = module._prepare_brandlagen(config, [grid], tmp_path / "prepared.gpkg")
    assert np.all(module._optional_burn_values(prepared, grid) == 0)
