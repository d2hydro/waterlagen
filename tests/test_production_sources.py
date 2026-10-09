from unittest.mock import create_autospec

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from waterlagen._sources import SourcePreparation
from waterlagen.ahn import productie as ahn
from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik import sources


def test_authority_and_named_area_use_shared_geometry_and_crs(tmp_path):
    from waterlagen.administratieve_gebieden.download import WATERSCHAPSGRENZEN_FILENAME
    from waterlagen.areas import NAMED_AREAS, resolve_area

    store = DataStore(data_dir=tmp_path, _env_file=None)
    data = gpd.GeoDataFrame(
        {
            "naam": ["Aa en Maas", "Andere beheerder"],
            "code": ["38", "99"],
            "waterbeheerdercode": ["38", "99"],
            "nen3610id": ["one", "two"],
        },
        geometry=[box(100, 100, 200, 200), box(200, 200, 300, 300)],
        crs=28992,
    )
    data.to_file(
        store.administratieve_gebieden_dir / WATERSCHAPSGRENZEN_FILENAME,
        layer="waterschap",
    )
    area = resolve_area("38", store, SourcePreparation(offline=True))
    assert area.value == "waterschap_38"
    assert area.geometry.equals(data.geometry.iloc[0])
    assert area.crs == "EPSG:28992"
    named = resolve_area("alkmaar", store, SourcePreparation(offline=True))
    assert named.geometry.equals(NAMED_AREAS["alkmaar"])
    with pytest.raises(ValueError, match="Geen gebied"):
        resolve_area("999", store, SourcePreparation(offline=True))


def test_landuse_prepares_all_standard_sources_and_reuses_them(tmp_path, monkeypatch):
    store = DataStore(data_dir=tmp_path, _env_file=None)
    paths = sources.FunctioneelLandgebruikSources.from_datastore(store)
    calls = []

    def write(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(len(calls)))
        return path

    targets = {
        "download_bag_light": paths.bag_gpkg,
        "download_brp": paths.brp_gpkg,
        "download_top10nl": paths.top10nl_gpkg,
        "_download_validated_zip_archive": store.bgt_dir
        / sources.DEFAULT_PREDEFINED_ARCHIVE,
        "prepare_bgt": paths.bgt_gpkg,
        "download_raster": store.source_data_dir / "liwo" / sources.FILENAME,
        "polygonize_selected": paths.buitendijks_gpkg,
        "download_hydamo": store.hydamo_dir / "hydamo.gpkg",
        "download_waterketen_damo": store.waterketen_damo_dir / "waterketen_damo.gpkg",
        "download_osm_drinkwater": store.source_data_dir
        / "osm"
        / "drinkwaterlocaties.gpkg",
    }
    for name, target in targets.items():

        def download(*args, _name=name, _target=target, **kwargs):
            calls.append(_name)
            return write(_target)

        monkeypatch.setattr(
            sources, name, create_autospec(getattr(sources, name), side_effect=download)
        )
    monkeypatch.setattr(sources, "ensure_land_boundary", lambda *args: None)
    prepared = sources.prepare_sources(store, SourcePreparation())
    assert set(calls) == set(targets)
    assert prepared.gemalen_gpkg == targets["download_hydamo"]
    assert prepared.rwzi_gpkg == targets["download_waterketen_damo"]
    assert prepared.drinking_water_gpkg == targets["download_osm_drinkwater"]
    calls.clear()
    sources.prepare_sources(store, SourcePreparation(offline=True))
    assert calls == []
    sources.prepare_sources(store, SourcePreparation(refresh=True))
    assert set(calls) == set(targets)


def test_ahn_uses_cached_index_tiles_and_stable_vrt_offline(tmp_path, monkeypatch):
    store = DataStore(data_dir=tmp_path, _env_file=None)
    index = gpd.GeoDataFrame(
        {"tile_id": ["one", "two"]},
        geometry=[box(0, 0, 2, 2), box(2, 0, 4, 2)],
        crs=28992,
    )
    index.to_file(store.ahn_dir / "ahn_dtm_05_index.gpkg", layer="tiles")
    tile = store.ahn_dir / "dtm_05" / "one.tif"
    tile.parent.mkdir()
    with rasterio.open(
        tile,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="float32",
        transform=from_origin(0, 2, 1, 1),
        crs=28992,
    ) as output:
        output.write(np.ones((2, 2), dtype="float32"), 1)

    def no_download(*args, **kwargs):
        pytest.fail("Offline production must not download")

    monkeypatch.setattr(ahn, "download_ahn", no_download)
    monkeypatch.setattr(ahn, "get_tiles_features", no_download)
    vrt = tmp_path / "run" / "ahn.vrt"
    area = box(0.5, 0.5, 1.5, 1.5)
    ahn.prepare_ahn(store, area, vrt, SourcePreparation(offline=True))
    modified = vrt.stat().st_mtime_ns
    ahn.prepare_ahn(store, area, vrt, SourcePreparation(offline=True))
    assert vrt.stat().st_mtime_ns == modified
    with rasterio.open(vrt) as raster:
        assert raster.bounds == (0, 0, 2, 2)
    with pytest.raises(FileNotFoundError, match="two.tif"):
        ahn.prepare_ahn(store, box(1, 0, 3, 2), vrt, SourcePreparation(offline=True))
