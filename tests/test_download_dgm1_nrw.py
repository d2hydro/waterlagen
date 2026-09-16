import importlib
import sys
from pathlib import Path
from types import ModuleType

import geopandas as gpd
import numpy as np
import pytest
import rasterio
import requests
from rasterio.transform import from_origin
from shapely.geometry import box

from waterlagen._downloads import FileDownload
from waterlagen.settings import settings


@pytest.fixture
def downloader(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = importlib.import_module("waterlagen.dgm1.download")
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    return module


@pytest.fixture
def script_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("download_dgm1_nrw")


def test_download_retries_then_reuses_valid_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, downloader: ModuleType
) -> None:
    filename = "dgm1_32_288_5736_1_nw_2024.tif"
    url = downloader.BASE_URL + filename
    url_list = tmp_path / "urls.txt"
    url_list.write_text(f"{url}\n\n{url}\n", encoding="utf-8")
    assert downloader._read_urls(url_list) == [url]
    attempts = []

    def fake_download(url, target, **kwargs):
        attempts.append(url)
        path = tmp_path / "temporary.tif"
        if len(attempts) == 1:
            path.write_bytes(b"incomplete download")
        else:
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                width=1000,
                height=1000,
                count=1,
                dtype="float32",
                crs="EPSG:25832",
                transform=from_origin(288000, 5737000, 1, 1),
                compress="lzw",
            ) as raster:
                raster.write(np.ones((1000, 1000), dtype=np.float32), 1)
        size = path.stat().st_size
        return FileDownload(url, path, size, True, size)

    monkeypatch.setattr(downloader, "stream_download_to_temp", fake_download)
    target = downloader._download_tile(url, tmp_path)
    assert target == tmp_path / filename
    assert len(attempts) == 2
    original_bytes = target.read_bytes()
    assert downloader._download_tile(url, tmp_path) == target
    assert len(attempts) == 2
    assert target.read_bytes() == original_bytes
    assert not (tmp_path / "temporary.tif").exists()


def test_failed_download_preserves_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, downloader: ModuleType
) -> None:
    url = downloader.BASE_URL + "dgm1_32_288_5736_1_nw_2024.tif"
    target = tmp_path / url.rsplit("/", 1)[-1]
    target.write_bytes(b"previous incomplete file")
    attempts = []

    def fake_download(url, target, **kwargs):
        attempts.append(url)
        path = tmp_path / "temporary.tif"
        path.write_bytes(b"truncated")
        return FileDownload(url, path, path.stat().st_size, True, 100)

    monkeypatch.setattr(downloader, "stream_download_to_temp", fake_download)
    with pytest.raises(RuntimeError, match="Download mislukt"):
        downloader._download_tile(url, tmp_path)
    assert len(attempts) == 3
    assert target.read_bytes() == b"previous incomplete file"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("mode", ["interactive", "terminal"])
def test_download_entry_points(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script_module: ModuleType,
    mode: str,
) -> None:
    url_list = tmp_path / "urls.txt"
    monkeypatch.setattr(script_module, "configure_logging", lambda: None)
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        return tmp_path / "dgm1_nrw.vrt"

    monkeypatch.setattr(script_module, "_download_dgm1", fake_download)
    if mode == "interactive":
        monkeypatch.setattr(sys, "argv", ["ipykernel_launcher.py", "--f=kernel.json"])
        script_module.download_dgm1(url_list)
    else:
        monkeypatch.setattr(sys, "argv", ["download_dgm1_nrw.py", str(url_list)])
        script_module.main()
    assert len(calls) == 1
    assert calls[0]["url_list"] == url_list
    assert calls[0]["poly_mask"] is None


@pytest.mark.parametrize("with_file", [True, False])
def test_run_cell_ignores_kernel_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script_module: ModuleType,
    with_file: bool,
) -> None:
    script = Path(script_module.__file__)
    namespace = {"__name__": "__main__"}
    if with_file:
        namespace["__file__"] = str(tmp_path / "scripts" / script.name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, "ipykernel", ModuleType("ipykernel"))
    monkeypatch.setattr(sys, "argv", ["ipykernel_launcher.py", "--f=kernel.json"])

    # De hele cel moet de downloader bereiken, zonder argparse-fout of netwerk.
    with pytest.raises(ValueError, match="Geef een gebied op"):
        exec(  # noqa: S102 - voer ons eigen script uit zoals een Interactive-cel
            compile(script.read_text(encoding="utf-8"), str(script), "exec"), namespace
        )


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch, downloader: ModuleType) -> None:
    names = [
        "dgm1_32_288_5736_1_nw_2022.tif",
        "dgm1_32_288_5736_1_nw_2024.tif",
        "dgm1_32_289_5736_1_nw_2024.tif",
    ]
    files = "".join(f'<file name="{name}" />' for name in names)
    response = requests.Response()
    response.status_code = 200
    response._content = (
        f"<opengeodata><datasets><dataset><files>{files}</files>"
        "</dataset></datasets></opengeodata>"
    ).encode()
    monkeypatch.setattr(downloader.requests, "get", lambda *a, **kw: response)


def test_catalog_selects_latest_tile_in_project_crs(
    catalog: None, downloader: ModuleType
) -> None:
    mask = (
        gpd.GeoSeries([box(288100, 5736100, 288900, 5736900)], crs=25832)
        .to_crs(settings.crs)
        .iloc[0]
    )

    tiles = downloader.get_tiles_features(poly_mask=mask)

    assert tiles.index.tolist() == ["32_288_5736"]
    assert tiles.year.tolist() == [2024]
    assert tiles.crs == settings.crs
    assert tiles.url.iloc[0].endswith("dgm1_32_288_5736_1_nw_2024.tif")
    assert downloader.get_tiles_features(
        select_indices=["32_289_5736"]
    ).index.tolist() == ["32_289_5736"]
    with pytest.raises(ValueError, match="Unknown or unselected"):
        downloader.get_tiles_features(poly_mask=mask, select_indices=["32_289_5736"])


def test_download_builds_vrt_of_selected_tiles_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    catalog: None,
    downloader: ModuleType,
) -> None:
    selected = tmp_path / "dgm1_32_288_5736_1_nw_2024.tif"
    unrelated = tmp_path / "dgm1_32_289_5736_1_nw_2024.tif"
    for path, x in [(selected, 288000), (unrelated, 289000)]:
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            count=1,
            width=1000,
            height=1000,
            dtype="float32",
            crs=25832,
            transform=from_origin(x, 5737000, 1, 1),
            compress="lzw",
        ) as output:
            output.write(np.ones((1000, 1000), dtype="float32"), 1)

    def no_download(*args, **kwargs):
        pytest.fail("Valid existing tile should be reused")

    monkeypatch.setattr(downloader, "stream_download_to_temp", no_download)
    vrt = downloader.download_dgm1(tmp_path, select_indices=["32_288_5736"])

    with rasterio.open(vrt) as source:
        assert source.bounds == (288000, 5736000, 289000, 5737000)
        assert source.crs.to_epsg() == 25832
        assert source.scales == (1.0,)
        np.testing.assert_array_equal(source.read(1), 1)
    assert unrelated.is_file()

    # A forced refresh failure must preserve the original tile and VRT.
    original_tile = selected.read_bytes()
    original_vrt = vrt.read_bytes()

    def fail_download(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(downloader, "stream_download_to_temp", fail_download)
    with pytest.raises(RuntimeError, match="DGM1 download failed"):
        downloader.download_dgm1(
            tmp_path, select_indices=["32_288_5736"], missing_only=False, retries=1
        )
    assert selected.read_bytes() == original_tile
    assert vrt.read_bytes() == original_vrt


@pytest.mark.parametrize("payload", [b"not XML", b"<html />", b"<opengeodata />"])
def test_catalog_rejects_invalid_response(
    monkeypatch: pytest.MonkeyPatch,
    downloader: ModuleType,
    payload: bytes,
) -> None:
    response = requests.Response()
    response.status_code = 200
    response._content = payload
    monkeypatch.setattr(downloader.requests, "get", lambda *a, **kw: response)
    with pytest.raises(ValueError, match="DGM1 tile index"):
        downloader.get_tiles_features()


def test_download_requires_selection(downloader: ModuleType) -> None:
    with pytest.raises(ValueError, match="Supply poly_mask"):
        downloader.download_dgm1()


def test_download_rejects_empty_selection(
    catalog: None, downloader: ModuleType
) -> None:
    with pytest.raises(ValueError, match="No DGM1 tiles"):
        downloader.download_dgm1(poly_mask=box(0, 0, 1, 1))


def test_script_uses_mask_in_configured_crs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script_module: ModuleType,
) -> None:
    mask_path = tmp_path / "area.gpkg"
    original = gpd.GeoDataFrame(
        geometry=[box(288000, 5736000, 289000, 5737000)], crs=25832
    )
    original.to_file(mask_path, layer="area", driver="GPKG")
    calls = []
    monkeypatch.setattr(script_module, "_download_dgm1", lambda **kw: calls.append(kw))
    monkeypatch.setattr(script_module, "configure_logging", lambda: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["download_dgm1_nrw.py", "--mask", str(mask_path), "--layer", "area"],
    )
    script_module.main()
    assert calls[0]["url_list"] is None
    assert calls[0]["poly_mask"].equals(original.to_crs(settings.crs).geometry.iloc[0])
