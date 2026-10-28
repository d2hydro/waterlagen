"""Public burn-source preparation using small local data and mocked downloads."""

import json
import socket
import zipfile
from dataclasses import replace

import geopandas as gpd
import pytest
import requests
from shapely.geometry import LineString, MultiPolygon, box

from waterlagen._production import _file_identity, production_run
from waterlagen._sources import SourcePreparation
from waterlagen.afwateringseenheden import (
    Brandlaag,
    BrandlagenConfig,
    read_brandlagen_config,
)
from waterlagen.afwateringseenheden import brand_sources as module
from waterlagen.afwateringseenheden.brandlagen import _brand_identity
from waterlagen.bgt.duikers import prepare_bgt_culverts
from waterlagen.datastore import DataStore
from waterlagen.osm_waterlopen import WATERWAY_LAYERS


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("No real download allowed")

    monkeypatch.setattr(requests.sessions.Session, "request", fail)
    monkeypatch.setattr(socket.socket, "connect", fail)


@pytest.fixture
def store(tmp_path):
    return DataStore(
        data_dir=tmp_path,
        source_data_dir=tmp_path / "source_data",
        processed_data_dir=tmp_path / "processed_data",
        _env_file=None,
    )


def write(path, layer, geometries=None, **attributes):
    path.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(
        attributes,
        geometry=geometries if geometries is not None else [box(1, 1, 2, 2)],
        crs=28992,
    ).to_file(path, layer=layer, driver="GPKG")
    return path


def config(store, provider="osm", layer="osm_canals", path=None):
    culvert = layer in {"bgt_duiker", "osm_culvert"}
    role = "duiker" if culvert else "water"
    if layer == "bgt_wegdeel":
        role = "overig"
    return BrandlagenConfig(
        (
            Brandlaag(
                path or store.source_data_dir / f"{layer}.gpkg",
                layer,
                rol=role,
                bron=provider if culvert else None,
                openbare_bron=provider,
            ),
        ),
        brandwaarde=-5,
        prioriteit=1,
    )


def prepare(conf, store, bounds=(0, 0, 10, 10), **options):
    reuse_only = options.pop("reuse_only", False)
    return module.prepare_brand_sources(
        conf, store, box(*bounds), SourcePreparation(**options), reuse_only=reuse_only
    )


@pytest.fixture
def osm_download(monkeypatch):
    calls = []

    def download(bounds, target_path=None, *, waterway=None, **kwargs):
        layer = "osm_culvert" if waterway is None else WATERWAY_LAYERS[waterway]
        calls.append((layer, bounds))
        write(target_path, layer, [LineString([(1, 1), (2, 2)])])
        policy = (
            "culverts_v1"
            if waterway is None
            else f"open_{layer.removeprefix('osm_')}_v1"
        )
        target_path.with_suffix(".json").write_text(
            json.dumps(
                {
                    "selection": {
                        "policy": policy,
                        "crs": "EPSG:28992",
                        "bounds": list(bounds),
                    },
                    "output": _file_identity(target_path),
                }
            )
        )
        return target_path

    monkeypatch.setattr(module, "download_osm_waterlopen", download)
    monkeypatch.setattr(module, "download_osm_culverts", download)
    return calls


@pytest.fixture
def bgt_requests(monkeypatch):
    calls = []

    def request(featuretypes, poly_mask):
        calls.append((featuretypes, poly_mask))
        return "request-id"

    monkeypatch.setattr(module, "request_download", request)
    monkeypatch.setattr(
        module, "poll_downloadstatus", lambda request_id: "https://example.test/bgt.zip"
    )
    return calls


def test_schema_is_explicit_and_keeps_relative_paths(tmp_path):
    toml = tmp_path / "invoer" / "brandlagen.toml"
    toml.parent.mkdir()
    toml.write_text(
        '[[lagen]]\npath="../data/osm.gpkg"\nlayer="osm_canals"\nrol="water"\nopenbare_bron="osm"\n'
    )
    parsed = read_brandlagen_config(toml)
    assert parsed.lagen[0].path == tmp_path / "data/osm.gpkg"
    assert parsed.lagen[0].openbare_bron == "osm"
    with pytest.raises(ValueError, match="niet-ondersteunde"):
        replace(parsed.lagen[0], openbare_bron="bgt")
    with pytest.raises(ValueError, match="duikers vereisen"):
        replace(parsed.lagen[0], layer="osm_culvert")


@pytest.mark.parametrize("layer", [*WATERWAY_LAYERS.values(), "osm_culvert"])
def test_osm_only_selected_layer_downloaded_with_full_context(
    store, osm_download, layer
):
    selected = config(store, layer=layer)
    result = prepare(selected, store, (178000, 388000, 192000, 402000))
    assert osm_download == [(layer, (178000, 388000, 192000, 402000))]
    assert result.config.lagen[0].path.exists()
    assert result.inputs["brandbron_0_metadata"].exists()
    assert (
        prepare(selected, store, (180000, 390000, 190000, 400000), offline=True).config
        == result.config
    )
    assert len(osm_download) == 1


def test_osm_coverage_offline_refresh_and_resume(store, osm_download):
    selected = config(store)
    with pytest.raises(FileNotFoundError, match="offline"):
        prepare(selected, store, offline=True)
    prepare(selected, store)
    with pytest.raises(FileNotFoundError, match="dekking"):
        prepare(selected, store, (-1, -1, 20, 20), offline=True)
    with pytest.raises(ValueError, match="nieuwe --run-id"):
        prepare(selected, store, (-1, -1, 20, 20), reuse_only=True)
    assert len(osm_download) == 1
    prepare(selected, store, (-1, -1, 20, 20))
    prepare(selected, store, (-1, -1, 20, 20), refresh=True)
    assert len(osm_download) == 3


def test_local_and_unverified_public_files_are_never_replaced(store, osm_download):
    own = write(store.source_data_dir / "own.gpkg", "osm_canals")
    original = own.read_bytes()
    local = BrandlagenConfig((Brandlaag(own, "osm_canals"),))
    assert prepare(local, store, refresh=True).config == local
    assert osm_download == []
    public = config(store, path=own)
    result = prepare(public, store)
    assert result.config.lagen[0].path != own
    assert own.read_bytes() == original
    missing = BrandlagenConfig(
        (Brandlaag(own.with_name("missing.gpkg"), "osm_canals"),)
    )
    with pytest.raises(FileNotFoundError, match="Eigen lokale"):
        prepare(missing, store)
    assert len(osm_download) == 1


def test_native_osm_cache_can_be_reused_from_standard_path(store, osm_download):
    standard = store.source_data_dir / "osm/osm_canals.gpkg"
    prepare(config(store, path=standard), store, (-100, -100, 100, 100))
    selected = config(store, path=store.source_data_dir / "other.gpkg")
    assert prepare(selected, store, offline=True).config.lagen[0].path == standard
    assert len(osm_download) == 1


def test_national_top10_download_once_for_two_layers_and_refresh(store, monkeypatch):
    calls = []

    def download(download_dir, overwrite=True):
        calls.append(download_dir)
        target = download_dir / module.TOP10NL_FILENAME
        write(target, "top10nl_waterdeel_vlak")
        write(target, "top10nl_waterdeel_lijn", [LineString([(0, 0), (2, 2)])])
        return target

    monkeypatch.setattr(module, "download_top10nl", download)
    selected = config(store, "top10nl", "top10nl_waterdeel_vlak")
    selected = replace(
        selected,
        lagen=(
            *selected.lagen,
            replace(selected.lagen[0], layer="top10nl_waterdeel_lijn"),
        ),
    )
    with pytest.raises(FileNotFoundError, match="offline"):
        prepare(selected, store, offline=True)
    prepare(selected, store)
    prepare(selected, store, (-100, -100, 100, 100), offline=True)
    assert len(calls) == 1
    prepare(selected, store, refresh=True)
    assert len(calls) == 2


def test_failed_national_download_keeps_existing_output(store, monkeypatch):
    selected = config(store, "top10nl", "top10nl_waterdeel_vlak")
    path = selected.lagen[0].path
    write(path, selected.lagen[0].layer)
    module._save_manifest(path, "top10nl", None)
    before = path.read_bytes()

    def bad(download_dir, **kwargs):
        return write(download_dir / module.TOP10NL_FILENAME, "wrong_layer")

    monkeypatch.setattr(module, "download_top10nl", bad)
    with pytest.raises(ValueError, match="TOP10NL bevat"):
        prepare(selected, store, refresh=True)
    assert path.read_bytes() == before


def test_national_verified_cache_is_reused_without_replacing_custom_file(store):
    standard = store.top10nl_dir / module.TOP10NL_FILENAME
    write(standard, "top10nl_waterdeel_vlak")
    module._save_manifest(standard, "top10nl", None)
    own = write(store.source_data_dir / "own.gpkg", "top10nl_waterdeel_vlak")
    before = own.read_bytes()
    result = prepare(
        config(store, "top10nl", "top10nl_waterdeel_vlak", own), store, offline=True
    )
    assert result.config.lagen[0].path == standard
    assert own.read_bytes() == before


def test_modified_osm_cache_is_not_overwritten_and_missing_layer_is_not_reused(
    store, osm_download
):
    selected = config(store)
    first = prepare(selected, store)
    original = first.config.lagen[0].path
    write(original, "own_layer")
    edited = original.read_bytes()
    result = prepare(selected, store)
    assert result.config.lagen[0].path != original
    assert original.read_bytes() == edited
    assert len(osm_download) == 2
    wrong = config(store, layer="osm_streams")
    target = wrong.lagen[0].path
    write(target, "wrong_layer")
    target.with_suffix(".json").write_text(
        json.dumps(
            {
                "selection": {
                    "policy": "open_streams_v1",
                    "crs": "EPSG:28992",
                    "bounds": [0, 0, 10, 10],
                },
                "output": _file_identity(target),
            }
        )
    )
    with pytest.raises(FileNotFoundError, match="offline"):
        prepare(wrong, store, offline=True)


def test_public_source_identity_participates_in_run_compatibility(store, osm_download):
    selected = config(store)
    prepared = prepare(selected, store)

    def run(current, **kwargs):
        with production_run(
            store.processed_data_dir,
            "test",
            "gebied",
            run_id="test",
            parameters={"brandlagen": _brand_identity(current.config)},
            **kwargs,
        ) as active:
            active.record_inputs(current.inputs)

    run(prepared)
    run(prepare(selected, store, reuse_only=True), resume=True)
    assert len(osm_download) == 1
    prepare(selected, store, refresh=True)
    with pytest.raises(ValueError, match="andere instellingen"):
        run(prepare(selected, store, reuse_only=True), resume=True)


def test_bgt_culverts_keep_valid_lines_polygons_and_attributes(tmp_path):
    shapes = [
        LineString([(0, 1), (3, 1)]),
        MultiPolygon([box(1, 2, 2, 3)]),
        box(1, 1, 2, 2),
        box(30, 30, 31, 31),
        box(1, 1, 2, 2),
    ]
    source = write(
        tmp_path / "raw.gpkg",
        "bgt_kunstwerkdeel",
        shapes,
        **{
            "plus-type": ["duiker"] * 4 + ["stuw"],
            "bgt-status": ["bestaand", "bestaand", "vervallen", "bestaand", "bestaand"],
            "brandwaarde": [-7, -8, -9, -10, -11],
        },
    )
    target = prepare_bgt_culverts(source, tmp_path / "result.gpkg", box(0, 0, 10, 10))
    result = gpd.read_file(target, layer="bgt_duiker")
    assert result.bron_fid.tolist() == [1, 2]
    assert result.brandwaarde.tolist() == [-7, -8]
    assert result.geometry.iloc[0].equals(shapes[0])
    assert result.geometry.iloc[1].equals(shapes[1])


def test_real_bgt_conversion_and_cache_invalidation(
    store, tmp_path, monkeypatch, bgt_requests
):
    # Real GDAL conversion of a tiny mixed-geometry national-archive stand-in.
    gml = tmp_path / "bgt_kunstwerkdeel.gml"
    gpd.GeoDataFrame(
        {"plus_type": ["duiker", "duiker"], "bgt_status": ["bestaand", "bestaand"]},
        geometry=[LineString([(1, 1), (3, 3)]), box(4, 4, 5, 5)],
        crs=28992,
    ).to_file(gml, driver="GML")
    gml.write_text(
        gml.read_text(encoding="utf-8")
        .replace("plus_type", "plus-type")
        .replace("bgt_status", "bgt-status"),
        encoding="utf-8",
    )
    archive = store.bgt_dir / module.DEFAULT_PREDEFINED_ARCHIVE
    with zipfile.ZipFile(archive, "w") as stream:
        stream.write(gml, gml.name)
    module._save_manifest(archive, "bgt_archive", None)
    selected = config(store, "bgt", "bgt_duiker")
    result = prepare(selected, store, offline=True)
    assert len(gpd.read_file(result.config.lagen[0].path)) == 2
    before = _file_identity(result.config.lagen[0].path)
    prepare(selected, store, (-1, -1, 20, 20), offline=True)
    assert _file_identity(result.config.lagen[0].path) != before
    before = _file_identity(result.config.lagen[0].path)
    prepare(selected, store, (0, 0, 10, 10), offline=True)
    assert _file_identity(result.config.lagen[0].path) == before
    # Replacing the archive invalidates both converted kunstwerkdelen and selection.
    with zipfile.ZipFile(archive, "a") as stream:
        stream.writestr("version.txt", "changed")
    module._save_manifest(archive, "bgt_archive", None)
    with pytest.raises(ValueError, match="nieuwe --run-id"):
        prepare(selected, store, reuse_only=True)
    prepare(selected, store, offline=True)
    assert _file_identity(result.config.lagen[0].path) != before

    # Refresh replaces an older national preparation with the requested custom data.
    raw = store.bgt_dir / "brandlagen" / "bgt_kunstwerkdeel.gpkg"
    raw_before = _file_identity(raw)

    def custom_download(**kwargs):
        with zipfile.ZipFile(kwargs["archive_path"], "w") as stream:
            stream.write(gml, gml.name)

    monkeypatch.setattr(module, "_download_validated_zip_archive", custom_download)
    prepare(selected, store, refresh=True)
    assert len(bgt_requests) == 1
    assert _file_identity(raw) != raw_before
    raw_metadata = module._read_json(module._manifest(raw))
    assert raw_metadata["coverage"] == [0, 0, 10, 10]
    assert list(raw_metadata["sources"]) == [
        str((raw.parent / "gebied/bgt_kunstwerkdeel.zip").resolve())
    ]


@pytest.mark.parametrize("feature_type", ["waterdeel", "wegdeel"])
def test_bgt_prepares_only_requested_feature_type(store, monkeypatch, feature_type):
    archive = store.bgt_dir / module.DEFAULT_PREDEFINED_ARCHIVE
    archive.write_bytes(b"mock archive")
    module._save_manifest(archive, "bgt_archive", None)
    calls = []

    def convert(archive, output_dir, feature_type, **kwargs):
        calls.append(feature_type)
        return write(output_dir / "surface.gpkg", f"bgt_{feature_type}")

    monkeypatch.setattr(module, "prepare_surface_layer", convert)
    selected = config(store, "bgt", f"bgt_{feature_type}")
    prepare(selected, store, offline=True)
    prepare(selected, store, offline=True)
    prepare(selected, store, bounds=(-100, -100, 100, 100), reuse_only=True)
    assert calls == [feature_type]


@pytest.mark.parametrize("feature_type", ["waterdeel", "wegdeel"])
def test_bgt_refresh_downloads_archive_once_and_rebuilds_layer(
    store, monkeypatch, feature_type, bgt_requests
):
    selected = config(store, "bgt", f"bgt_{feature_type}")
    calls = []

    def download(**kwargs):
        calls.append("download")
        kwargs["archive_path"].write_bytes(str(len(calls)).encode())

    def convert(archive, output_dir, feature_type, **kwargs):
        calls.append("convert")
        return write(output_dir / "surface.gpkg", f"bgt_{feature_type}")

    monkeypatch.setattr(module, "_download_validated_zip_archive", download)
    monkeypatch.setattr(module, "prepare_surface_layer", convert)
    prepare(selected, store)
    prepare(selected, store, refresh=True)
    assert calls == ["download", "convert", "download", "convert"]
    assert [types for types, _ in bgt_requests] == [(feature_type,), (feature_type,)]
    with pytest.raises(ValueError, match="vernieuwen"):
        prepare(selected, store, refresh=True, offline=True)
    with pytest.raises(ValueError, match="vernieuwen"):
        prepare(selected, store, refresh=True, reuse_only=True)


def test_road_toml_requires_ordinary_burn_role(tmp_path):
    toml = tmp_path / "brandlagen.toml"
    toml.write_text(
        '[[lagen]]\npath="data/bgt_wegdeel.gpkg"\nlayer="bgt_wegdeel"\n'
        'openbare_bron="bgt"\nbrandwaarde=2\nprioriteit=3\n'
    )
    layer = read_brandlagen_config(toml).lagen[0]
    assert layer.rol == "overig"
    assert layer.brandwaarde == 2 and layer.prioriteit == 3
    assert layer.path == tmp_path / "data/bgt_wegdeel.gpkg"
    for role in ("water", "duiker"):
        with pytest.raises(ValueError, match="wegdelen vereisen rol=overig"):
            replace(layer, rol=role, bron="bgt")


def test_roads_require_cached_sources_offline_and_keep_own_input_local(store):
    selected = config(store, "bgt", "bgt_wegdeel")
    with pytest.raises(FileNotFoundError):
        prepare(selected, store, offline=True)
    with pytest.raises(ValueError, match="nieuwe --run-id"):
        prepare(selected, store, reuse_only=True)
    local = replace(selected.lagen[0], openbare_bron=None)
    with pytest.raises(FileNotFoundError, match="Eigen lokale"):
        prepare(BrandlagenConfig((local,)), store)
    write(local.path, local.layer, brandwaarde=[2.5], prioriteit=[4])
    before = local.path.read_bytes()
    result = prepare(BrandlagenConfig((local,)), store, refresh=True)
    assert result.config.lagen == (local,)
    assert local.path.read_bytes() == before


def test_water_and_roads_use_separate_requests_without_replacing_each_other(
    store, monkeypatch, bgt_requests
):
    downloads = []
    conversions = []

    def download(**kwargs):
        downloads.append(kwargs["archive_path"])
        kwargs["archive_path"].write_bytes(b"mock custom archive")

    def convert(archive, output_dir, feature_type):
        conversions.append(feature_type)
        return write(output_dir / "layer.gpkg", f"bgt_{feature_type}")

    monkeypatch.setattr(module, "_download_validated_zip_archive", download)
    monkeypatch.setattr(module, "prepare_surface_layer", convert)
    shared_path = store.bgt_dir / "bgt.gpkg"
    water = config(store, "bgt", "bgt_waterdeel", shared_path).lagen[0]
    roads = config(store, "bgt", "bgt_wegdeel", shared_path).lagen[0]
    selected = BrandlagenConfig((water, roads), brandwaarde=1, prioriteit=2)
    result = prepare(selected, store, refresh=True)
    assert conversions == ["waterdeel", "wegdeel"]
    assert len(downloads) == 2
    assert [types for types, _ in bgt_requests] == [("waterdeel",), ("wegdeel",)]
    water_path, road_path = (layer.path for layer in result.config.lagen)
    assert water_path != road_path
    assert module._layer_exists(water_path, "bgt_waterdeel")
    assert module._layer_exists(road_path, "bgt_wegdeel")
    reused = prepare(selected, store, offline=True, reuse_only=True)
    assert reused.config == result.config
    assert len(downloads) == 2 and len(conversions) == 2


def test_empty_configuration_and_invalid_local_input_never_download(
    store, osm_download
):
    result = prepare(BrandlagenConfig(), store)
    assert result.config.lagen == () and result.inputs == {}
    selected = config(store)
    selected = replace(
        selected,
        lagen=(
            *selected.lagen,
            Brandlaag(store.source_data_dir / "missing.gpkg", "eigen"),
        ),
    )
    with pytest.raises(FileNotFoundError, match="Eigen lokale"):
        prepare(selected, store)
    assert osm_download == []


def test_unverified_bgt_archive_is_preserved_during_refresh(
    store, monkeypatch, bgt_requests
):
    archive = store.bgt_dir / module.DEFAULT_PREDEFINED_ARCHIVE
    archive.write_bytes(b"user archive without provenance")

    def download(**kwargs):
        kwargs["archive_path"].write_bytes(b"mock custom archive")

    monkeypatch.setattr(module, "_download_validated_zip_archive", download)
    monkeypatch.setattr(
        module,
        "prepare_surface_layer",
        lambda archive, output_dir, feature_type: write(
            output_dir / "water.gpkg", "bgt_waterdeel"
        ),
    )
    prepare(config(store, "bgt", "bgt_waterdeel"), store, refresh=True)
    assert archive.read_bytes() == b"user archive without provenance"
    cached = store.bgt_dir / "brandlagen" / "gebied" / "bgt_waterdeel.zip"
    assert cached.read_bytes() == b"mock custom archive"
    assert module._manifest(cached).is_file()


@pytest.mark.parametrize("feature_type", ["waterdeel", "wegdeel"])
def test_regional_bgt_coverage_reuse_offline_and_refresh(
    store, monkeypatch, bgt_requests, feature_type
):
    def download(**kwargs):
        kwargs["archive_path"].write_bytes(str(len(bgt_requests)).encode())

    monkeypatch.setattr(module, "_download_validated_zip_archive", download)
    monkeypatch.setattr(
        module,
        "prepare_surface_layer",
        lambda archive, output_dir, name: write(
            output_dir / "layer.gpkg", f"bgt_{name}"
        ),
    )
    selected = config(store, "bgt", f"bgt_{feature_type}")
    bounds = (178000, 388000, 192000, 402000)
    result = prepare(selected, store, bounds)
    assert len(bgt_requests) == 1
    assert bgt_requests[0][0] == (feature_type,)
    assert bgt_requests[0][1].equals(box(*bounds))
    target = result.config.lagen[0].path
    assert module._read_json(module._manifest(target))["coverage"] == list(bounds)
    smaller = (180000, 390000, 185000, 395000)
    assert prepare(selected, store, smaller, offline=True).config == result.config
    prepare(selected, store, bounds, reuse_only=True)
    assert len(bgt_requests) == 1
    larger = (170000, 380000, 200000, 410000)
    before = target.read_bytes()
    with pytest.raises(FileNotFoundError, match="offline"):
        prepare(selected, store, larger, offline=True)
    with pytest.raises(ValueError, match="nieuwe --run-id"):
        prepare(selected, store, larger, reuse_only=True)
    assert target.read_bytes() == before and len(bgt_requests) == 1
    prepare(selected, store, larger)
    assert len(bgt_requests) == 2
    assert bgt_requests[-1][1].equals(box(*larger))
    prepare(selected, store, larger, refresh=True)
    assert len(bgt_requests) == 3
    before = target.read_bytes()

    def broken(archive, output_dir, name):
        raise ValueError("invalid downloaded layer")

    monkeypatch.setattr(module, "prepare_surface_layer", broken)
    with pytest.raises(ValueError, match="invalid downloaded"):
        prepare(selected, store, larger, refresh=True)
    assert target.read_bytes() == before


def test_regional_bgt_culverts_keep_lines_and_polygons(
    store, tmp_path, monkeypatch, bgt_requests
):
    shapes = [
        LineString([(184000, 392000), (184005, 392005)]),
        box(184010, 392010, 184015, 392015),
    ]
    gml = tmp_path / "bgt_kunstwerkdeel.gml"
    gpd.GeoDataFrame(
        {"plus_type": ["duiker", "duiker"], "bgt_status": ["bestaand", "bestaand"]},
        geometry=shapes,
        crs=28992,
    ).to_file(gml, driver="GML")
    gml.write_text(
        gml.read_text(encoding="utf-8")
        .replace("plus_type", "plus-type")
        .replace("bgt_status", "bgt-status"),
        encoding="utf-8",
    )

    def download(**kwargs):
        with zipfile.ZipFile(kwargs["archive_path"], "w") as stream:
            stream.write(gml, gml.name)
            stream.writestr("revision.txt", str(len(bgt_requests)))

    monkeypatch.setattr(module, "_download_validated_zip_archive", download)
    selected = config(store, "bgt", "bgt_duiker")
    bounds = (178000, 388000, 192000, 402000)
    result = prepare(selected, store, bounds)
    assert bgt_requests[0][0] == ("kunstwerkdeel",)
    assert bgt_requests[0][1].equals(box(*bounds))
    target = result.config.lagen[0].path
    features = gpd.read_file(target, layer="bgt_duiker")
    assert features.geom_type.tolist() == ["LineString", "Polygon"]
    assert all(
        actual.equals(expected) for actual, expected in zip(features.geometry, shapes)
    )
    identity = _file_identity(target)
    prepare(selected, store, bounds, offline=True, reuse_only=True)
    assert _file_identity(target) == identity
    larger = (170000, 380000, 200000, 410000)
    with pytest.raises(FileNotFoundError, match="offline"):
        prepare(selected, store, larger, offline=True)
    prepare(selected, store, larger)
    assert len(bgt_requests) == 2
    identity = _file_identity(target)
    prepare(selected, store, larger, refresh=True)
    assert len(bgt_requests) == 3
    assert _file_identity(target) != identity


def test_regional_bgt_geofilter_uses_rd_and_preserves_unknown_archive(
    store, monkeypatch, bgt_requests
):
    monkeypatch.setattr(module.settings, "crs", "EPSG:4326")

    def download(**kwargs):
        kwargs["archive_path"].write_bytes(b"custom archive")

    monkeypatch.setattr(module, "_download_validated_zip_archive", download)
    bounds = (5.0, 51.0, 5.1, 51.1)
    archive = module._archive(store, SourcePreparation(), "waterdeel", bounds)
    requested = bgt_requests[0][1]
    assert requested.bounds[0] > 100000 and requested.bounds[1] > 300000
    assert module._read_json(module._manifest(archive))["coverage"] == list(bounds)
    archive.write_bytes(b"user modified")
    with pytest.raises(ValueError, match="Onbekend of gewijzigd"):
        module._archive(store, SourcePreparation(refresh=True), "waterdeel", bounds)
    assert archive.read_bytes() == b"user modified"
    assert len(bgt_requests) == 1


def test_production_prepares_full_tile_context_before_ahn_and_resume_is_read_only(
    store, monkeypatch, osm_download
):
    from waterlagen.afwateringseenheden import productie
    from waterlagen.areas import area_from_bounds

    area = area_from_bounds((184285, 392054, 185285, 393054))
    selected = config(store)
    monkeypatch.setattr(productie, "require_pcraster", lambda: None)
    monkeypatch.setattr(productie, "_prepare_brandlagen", lambda *args: None)

    def stop(*args):
        raise RuntimeError("stop before heavy sources")

    monkeypatch.setattr(productie, "ensure_land_boundary", stop)
    for reuse in (False, True):
        with pytest.raises(RuntimeError, match="stop before"):
            productie.main(
                store, area=area, run_id="test", brandlagen=selected, resume=reuse
            )
    assert osm_download == [("osm_canals", (178000, 388000, 192000, 402000))]
    run = (
        store.processed_data_dir / "afwateringseenheden" / area.value / "test/run.json"
    )
    metadata = json.loads(run.read_text())
    assert metadata["parameters"]["openbare_brandbronnen"][0]["openbare_bron"] == "osm"
    recorded = metadata["parameters"]["openbare_brandbron_metadata"][
        "brandbron_0_metadata"
    ]
    assert recorded["path"] == str(selected.lagen[0].path.with_suffix(".json"))
    assert recorded["size"] > 0
    before = selected.lagen[0].path.read_bytes()
    with pytest.raises(ValueError, match="vernieuwen"):
        productie.main(
            store,
            area=area,
            run_id="test",
            brandlagen=selected,
            resume=True,
            refresh_sources=True,
        )
    assert selected.lagen[0].path.read_bytes() == before
