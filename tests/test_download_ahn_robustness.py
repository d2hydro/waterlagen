import io
import logging
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

import waterlagen.ahn.download as ahn_download


class FakeResponse:
    def __init__(
        self,
        payload: bytes,
        *,
        url: str = "https://example.com/tile.tif",
        content_type: str = "image/tiff",
        error: Exception | None = None,
    ):
        self.content = payload
        self.url = url
        self.headers = {"Content-Type": content_type}
        self.error = error

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error


class FakeAHNService:
    def __init__(self, service: str):
        self.service = service

    def _validate_inputs(self, *, cell_size: str, ahn_version: int) -> None:
        return None

    def download_url_field(
        self,
        *,
        model: str,
        cell_size: str,
        ahn_version: int,
    ) -> str:
        return "download_url"


def _tiff_bytes(*, value: float = 1.25) -> bytes:
    data = np.full((32, 32), value, dtype=np.float32)
    profile = {
        "driver": "GTiff",
        "height": data.shape[0],
        "width": data.shape[1],
        "count": 1,
        "dtype": data.dtype,
        "crs": "EPSG:28992",
        "transform": from_origin(0, 32, 1, 1),
        "nodata": -9999.0,
    }
    with MemoryFile() as memory_file:
        with memory_file.open(**profile) as destination:
            destination.write(data, 1)
        return memory_file.read()


def _zip_tiff(payload: bytes) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("tile.tif", payload)
    return output.getvalue()


def _write_valid_tiff(path: Path, *, value: float = 1.25) -> None:
    path.write_bytes(_tiff_bytes(value=value))


def _tiles(*tile_indices: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "download_url": [
                f"https://example.com/{tile_index}.tif" for tile_index in tile_indices
            ]
        },
        index=list(tile_indices),
    )


def _configure_download(monkeypatch, tiles: pd.DataFrame) -> None:
    monkeypatch.setattr(ahn_download, "AHNService", FakeAHNService)
    monkeypatch.setattr(ahn_download, "get_tiles_features", lambda **kwargs: tiles)


def _tile_path(root: Path, tile_index: str = "tile_1") -> Path:
    return root / "dtm_05" / f"{tile_index}.tif"


def _temporary_tiles(tile_path: Path) -> list[Path]:
    return list(tile_path.parent.glob(f".{tile_path.name}.*.tif"))


def test_missing_tile_is_downloaded_to_a_temporary_tiff(monkeypatch, tmp_path):
    _configure_download(monkeypatch, _tiles("tile_1"))
    payload = _tiff_bytes()
    monkeypatch.setattr(
        ahn_download.requests,
        "get",
        lambda url: FakeResponse(payload, url=url),
    )
    validations: list[Path] = []
    original_validate = ahn_download._is_valid_ahn_tile

    def track_validation(path: Path) -> bool:
        validations.append(Path(path))
        return original_validate(path)

    original_replace = Path.replace

    def track_replace(path: Path, target: Path):
        assert path in validations
        assert path.name.startswith(".tile_1.tif.")
        return original_replace(path, target)

    monkeypatch.setattr(ahn_download, "_is_valid_ahn_tile", track_validation)
    monkeypatch.setattr(Path, "replace", track_replace)

    result = ahn_download.download_ahn(
        ahn_dir=tmp_path,
        create_vrt=False,
        retries=1,
    )

    tile_path = _tile_path(tmp_path)
    assert result == tile_path.parent
    assert ahn_download._is_valid_ahn_tile(tile_path)
    assert _temporary_tiles(tile_path) == []


def test_valid_existing_tile_is_reused_with_missing_only(monkeypatch, tmp_path):
    _configure_download(monkeypatch, _tiles("tile_1"))
    tile_path = _tile_path(tmp_path)
    tile_path.parent.mkdir()
    _write_valid_tiff(tile_path)
    original_payload = tile_path.read_bytes()

    def fail_get(url: str):
        raise AssertionError("valid existing tile should not be downloaded")

    monkeypatch.setattr(ahn_download.requests, "get", fail_get)

    ahn_download.download_ahn(ahn_dir=tmp_path, create_vrt=False, retries=1)

    assert tile_path.read_bytes() == original_payload


def test_corrupt_existing_tile_is_removed_and_downloaded_again(
    monkeypatch, tmp_path, caplog
):
    _configure_download(monkeypatch, _tiles("tile_1"))
    tile_path = _tile_path(tmp_path)
    tile_path.parent.mkdir()
    tile_path.write_bytes(b"incomplete")
    payload = _tiff_bytes()
    monkeypatch.setattr(
        ahn_download.requests,
        "get",
        lambda url: FakeResponse(payload, url=url),
    )
    caplog.set_level(logging.WARNING, logger="waterlagen.ahn.download")

    ahn_download.download_ahn(ahn_dir=tmp_path, create_vrt=False, retries=1)

    assert ahn_download._is_valid_ahn_tile(tile_path)
    assert "invalid or incomplete; removing it before download" in caplog.text


def test_corrupt_tiff_response_retries_and_cleans_temporary_files(
    monkeypatch, tmp_path
):
    _configure_download(monkeypatch, _tiles("tile_1"))
    responses = iter([b"not a tiff", _tiff_bytes()])
    calls: list[str] = []

    def fake_get(url: str) -> FakeResponse:
        calls.append(url)
        return FakeResponse(next(responses), url=url)

    monkeypatch.setattr(ahn_download.requests, "get", fake_get)

    ahn_download.download_ahn(ahn_dir=tmp_path, create_vrt=False, retries=2)

    tile_path = _tile_path(tmp_path)
    assert len(calls) == 2
    assert ahn_download._is_valid_ahn_tile(tile_path)
    assert _temporary_tiles(tile_path) == []


def test_corrupt_zip_response_retries(monkeypatch, tmp_path):
    _configure_download(monkeypatch, _tiles("tile_1"))
    responses = iter(
        [
            FakeResponse(
                b"not a zip",
                url="https://example.com/tile.zip",
                content_type="application/zip",
            ),
            FakeResponse(_tiff_bytes()),
        ]
    )
    calls = []

    def fake_get(url: str) -> FakeResponse:
        calls.append(url)
        return next(responses)

    monkeypatch.setattr(ahn_download.requests, "get", fake_get)

    ahn_download.download_ahn(ahn_dir=tmp_path, create_vrt=False, retries=2)

    assert len(calls) == 2
    assert ahn_download._is_valid_ahn_tile(_tile_path(tmp_path))


def test_overview_error_retries(monkeypatch, tmp_path):
    _configure_download(monkeypatch, _tiles("tile_1"))
    original_write = ahn_download._write_ahn_tile
    calls = 0

    def fail_first_overview(path: Path, payload: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("overview build failed")
        original_write(path, payload)

    monkeypatch.setattr(ahn_download, "_write_ahn_tile", fail_first_overview)
    monkeypatch.setattr(
        ahn_download.requests,
        "get",
        lambda url: FakeResponse(_tiff_bytes(), url=url),
    )

    ahn_download.download_ahn(ahn_dir=tmp_path, create_vrt=False, retries=2)

    assert calls == 2
    assert ahn_download._is_valid_ahn_tile(_tile_path(tmp_path))


def test_retry_stops_after_maximum_and_reports_all_failed_tiles(monkeypatch, tmp_path):
    _configure_download(monkeypatch, _tiles("tile_1", "tile_2"))
    calls: list[str] = []

    def fake_get(url: str) -> FakeResponse:
        calls.append(url)
        return FakeResponse(b"invalid", url=url)

    monkeypatch.setattr(ahn_download.requests, "get", fake_get)

    with pytest.raises(RuntimeError, match="tile_1.*tile_2") as exc_info:
        ahn_download.download_ahn(ahn_dir=tmp_path, create_vrt=False, retries=2)

    assert len(calls) == 4
    assert "https://example.com/tile_1.tif" in str(exc_info.value)
    assert "https://example.com/tile_2.tif" in str(exc_info.value)
    assert _temporary_tiles(_tile_path(tmp_path)) == []
    assert _temporary_tiles(_tile_path(tmp_path, "tile_2")) == []


def test_valid_existing_tile_survives_failed_replacement(monkeypatch, tmp_path):
    _configure_download(monkeypatch, _tiles("tile_1"))
    tile_path = _tile_path(tmp_path)
    tile_path.parent.mkdir()
    _write_valid_tiff(tile_path, value=2.5)
    original_payload = tile_path.read_bytes()
    monkeypatch.setattr(
        ahn_download.requests,
        "get",
        lambda url: FakeResponse(b"invalid", url=url),
    )

    with pytest.raises(RuntimeError, match="tile_1"):
        ahn_download.download_ahn(
            ahn_dir=tmp_path,
            create_vrt=False,
            missing_only=False,
            retries=2,
        )

    assert tile_path.read_bytes() == original_payload
    assert ahn_download._is_valid_ahn_tile(tile_path)


def test_direct_tiff_response_keeps_meter_to_centimeter_conversion(
    monkeypatch, tmp_path
):
    _configure_download(monkeypatch, _tiles("tile_1"))
    monkeypatch.setattr(ahn_download.settings, "m_to_cm", True)
    monkeypatch.setattr(
        ahn_download.requests,
        "get",
        lambda url: FakeResponse(_tiff_bytes(value=1.23), url=url),
    )

    ahn_download.download_ahn(ahn_dir=tmp_path, create_vrt=False, retries=1)

    with rasterio.open(_tile_path(tmp_path)) as source:
        assert source.dtypes[0] == "int16"
        assert source.scales == (0.01,)
        assert source.read(1)[0, 0] == 123


def test_direct_tiff_response_keeps_meter_values_when_conversion_is_disabled(
    monkeypatch,
    tmp_path,
):
    _configure_download(monkeypatch, _tiles("tile_1"))
    monkeypatch.setattr(ahn_download.settings, "m_to_cm", False)
    monkeypatch.setattr(
        ahn_download.requests,
        "get",
        lambda url: FakeResponse(_tiff_bytes(value=1.23), url=url),
    )

    ahn_download.download_ahn(ahn_dir=tmp_path, create_vrt=False, retries=1)

    with rasterio.open(_tile_path(tmp_path)) as source:
        assert source.dtypes[0] == "float32"
        assert source.scales == (1.0,)
        assert source.read(1)[0, 0] == pytest.approx(1.23)


def test_zip_response_with_tiff_is_supported(monkeypatch, tmp_path):
    _configure_download(monkeypatch, _tiles("tile_1"))
    payload = _zip_tiff(_tiff_bytes())
    monkeypatch.setattr(
        ahn_download.requests,
        "get",
        lambda url: FakeResponse(
            payload,
            url="https://example.com/tile.zip",
            content_type="application/zip",
        ),
    )

    ahn_download.download_ahn(ahn_dir=tmp_path, create_vrt=False, retries=1)

    assert ahn_download._is_valid_ahn_tile(_tile_path(tmp_path))


@pytest.mark.parametrize(
    "retries, error", [(True, TypeError), (1.5, TypeError), (-1, ValueError)]
)
def test_download_ahn_validates_retries(monkeypatch, tmp_path, retries, error):
    _configure_download(monkeypatch, _tiles("tile_1"))

    with pytest.raises(error, match="retries"):
        ahn_download.download_ahn(
            ahn_dir=tmp_path,
            create_vrt=False,
            retries=retries,
        )


def test_zero_retries_makes_no_http_request(monkeypatch, tmp_path):
    _configure_download(monkeypatch, _tiles("tile_1"))

    def fail_get(url: str):
        raise AssertionError("zero retries should not make an HTTP request")

    monkeypatch.setattr(ahn_download.requests, "get", fail_get)

    with pytest.raises(RuntimeError, match="no download attempts configured"):
        ahn_download.download_ahn(ahn_dir=tmp_path, create_vrt=False, retries=0)


def test_logging_contains_tile_url_attempt_and_retry_reason(
    monkeypatch, tmp_path, caplog
):
    _configure_download(monkeypatch, _tiles("tile_1"))
    responses = iter([b"invalid", _tiff_bytes()])
    monkeypatch.setattr(
        ahn_download.requests,
        "get",
        lambda url: FakeResponse(next(responses), url=url),
    )
    caplog.set_level(logging.INFO, logger="waterlagen.ahn.download")

    ahn_download.download_ahn(ahn_dir=tmp_path, create_vrt=False, retries=2)

    assert "tile_1" in caplog.text
    assert "attempt 1/2" in caplog.text
    assert "https://example.com/tile_1.tif" in caplog.text
    assert "retrying" in caplog.text
