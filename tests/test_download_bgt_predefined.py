import io
import logging
import zipfile
from pathlib import Path

import geopandas as gpd
import pyogrio
import pytest
from shapely.geometry import Point

import waterlagen.bgt.download as bgt_download_module
from waterlagen._crs import format_crs, read_layer_crs_info, same_crs
from waterlagen._downloads import DownloadPayloadError, validate_geopackage
from waterlagen.bgt.download import (
    BGT_PREDEFINED_URL,
    _convert_bgt_zip_to_geopackage,
    _translate_gml_layer_to_geopackage,
    bgt_download,
    download_bgt,
)


class FakeStreamResponse:
    def __init__(
        self,
        payload: bytes,
        *,
        headers: dict[str, str] | None = None,
        stream_error: Exception | None = None,
    ):
        self.payload = payload
        self.headers = headers or {}
        self.stream_error = stream_error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size: int):
        midpoint = max(1, len(self.payload) // 2)
        yield self.payload[:midpoint]
        if self.stream_error is not None:
            raise self.stream_error
        yield self.payload[midpoint:]


def _zip_with_gml(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name in names:
            zf.writestr(name, "<gml />")
    return buffer.getvalue()


def _mock_download(monkeypatch, response: FakeStreamResponse):
    def fake_get(url, **kwargs):
        assert url == BGT_PREDEFINED_URL
        assert kwargs == {"stream": True, "allow_redirects": True, "timeout": 30}
        return response

    monkeypatch.setattr("waterlagen._downloads.requests.get", fake_get)


def _mock_gml_reader(monkeypatch, crs_by_layer: dict[str, str | None]):
    def fake_translate(
        gml_path, target_path, *, layer_name, expected_crs, append, **kwargs
    ):
        layer = Path(gml_path).stem
        crs = crs_by_layer[layer]
        if crs == "EPSG:4326":
            point = Point(5, 52)
        elif crs == "EPSG:3857":
            point = Point(556597, 6800125)
        else:
            point = Point(100000, 450000)
        if crs is None:
            bgt_download_module.logger.warning(
                f"Layer {layer_name} has no CRS. Assigning {format_crs(expected_crs)}."
            )
            gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[point], crs=expected_crs)
        else:
            if not same_crs(crs, expected_crs):
                bgt_download_module.logger.warning(
                    f"Layer {layer_name} CRS is {format_crs(crs)}, "
                    f"expected {format_crs(expected_crs)}. Reprojecting layer."
                )
            gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[point], crs=crs).to_crs(
                expected_crs
            )
        pyogrio.write_dataframe(
            gdf,
            target_path,
            layer=layer_name,
            driver="GPKG",
            append=append,
        )

    monkeypatch.setattr(
        "waterlagen.bgt.download._translate_gml_layer_to_geopackage",
        fake_translate,
    )


def _valid_gpkg(path: Path, *, layer: str = "old") -> bytes:
    gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[Point(100000, 450000)],
        crs="EPSG:28992",
    ).to_file(path, driver="GPKG", layer=layer)
    validate_geopackage(path)
    return path.read_bytes()


def _temp_files_for(target: Path) -> list[Path]:
    return list(target.parent.glob(f".{target.name}.*"))


def _temp_archives_for(archive: Path) -> list[Path]:
    return list(archive.parent.glob(f".{archive.name}.*.zip"))


def _spatial_crs_values(path: Path) -> dict[str, str | None]:
    return {
        info.layer: info.crs for info in read_layer_crs_info(path) if info.is_spatial
    }


def test_bgt_download_alias_points_to_download_bgt(monkeypatch):
    calls = []

    def fake_download_bgt(*args, **kwargs):
        calls.append((args, kwargs))
        return "download"

    monkeypatch.setattr(
        "waterlagen.bgt.download.download_bgt",
        fake_download_bgt,
    )

    assert bgt_download("dir", overwrite=False) == "download"
    assert calls == [(("dir",), {"overwrite": False})]


def test_gdal_translation_does_not_read_gml_into_geodataframe(monkeypatch, tmp_path):
    calls = []
    gml_path = tmp_path / "bgt_waterdeel.gml"
    gml_path.write_text("<gml />")

    def fail_read_file(*args, **kwargs):
        raise AssertionError("GML conversion should not load a GeoDataFrame")

    def fake_vector_translate(dest, src, **kwargs):
        calls.append((dest, src, kwargs))
        return object()

    source_dataset = object()
    monkeypatch.setattr("geopandas.read_file", fail_read_file)
    monkeypatch.setattr(
        "waterlagen.bgt.download.pyogrio.read_info",
        lambda path: {"crs": "EPSG:28992"},
    )
    monkeypatch.setattr(
        "waterlagen.bgt.download.gdal.VectorTranslate",
        fake_vector_translate,
    )
    monkeypatch.setattr(
        "waterlagen.bgt.download.gdal.OpenEx",
        lambda *args, **kwargs: source_dataset,
    )

    _translate_gml_layer_to_geopackage(
        gml_path,
        tmp_path / "bgt.gpkg",
        layer_name="bgt_waterdeel",
        expected_crs="EPSG:28992",
        append=False,
    )

    assert len(calls) == 1
    assert calls[0][0] == str(tmp_path / "bgt.gpkg")
    assert calls[0][1] is source_dataset


def test_gdal_translation_preserves_fields_and_xml_attributes(tmp_path):
    gml_path = tmp_path / "bgt_waterdeel.gml"
    gml_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gml:FeatureCollection
    xmlns:gml="http://www.opengis.net/gml"
    xmlns:bgt="https://example.com/bgt">
  <gml:featureMember>
    <bgt:waterdeel gml:id="waterdeel.1">
      <bgt:geometry>
        <gml:Point srsName="urn:ogc:def:crs:EPSG::28992">
          <gml:coordinates>100000,450000</gml:coordinates>
        </gml:Point>
      </bgt:geometry>
      <bgt:naam status="bestaand">eerste</bgt:naam>
    </bgt:waterdeel>
  </gml:featureMember>
  <gml:featureMember>
    <bgt:waterdeel gml:id="waterdeel.2">
      <bgt:geometry>
        <gml:Point srsName="urn:ogc:def:crs:EPSG::28992">
          <gml:coordinates>100001,450001</gml:coordinates>
        </gml:Point>
      </bgt:geometry>
      <bgt:naam status="gepland">tweede</bgt:naam>
      <bgt:laterVeld>alleen in tweede object</bgt:laterVeld>
    </bgt:waterdeel>
  </gml:featureMember>
</gml:FeatureCollection>
""",
        encoding="utf-8",
    )
    target_path = tmp_path / "bgt.gpkg"

    _translate_gml_layer_to_geopackage(
        gml_path,
        target_path,
        layer_name="bgt_waterdeel",
        expected_crs="EPSG:28992",
        append=False,
        source_crs="EPSG:28992",
    )

    result = pyogrio.read_dataframe(target_path, layer="bgt_waterdeel")
    assert {"gml_id", "naam_status", "naam", "laterVeld"} <= set(result.columns)
    assert result["gml_id"].tolist() == ["waterdeel.1", "waterdeel.2"]
    assert result["naam_status"].tolist() == ["bestaand", "gepland"]
    assert result["laterVeld"].tolist() == [None, "alleen in tweede object"]


def test_gdal_translation_formats_explicit_source_crs(monkeypatch, tmp_path):
    gml_path = tmp_path / "bgt_waterdeel.gml"
    gml_path.write_text("<gml />")
    calls = []

    def fail_read_info(*args, **kwargs):
        raise AssertionError("source_crs should skip GML CRS probing")

    def fake_options(**kwargs):
        return kwargs

    def fake_vector_translate(dest, src, **kwargs):
        calls.append((dest, src, kwargs))
        return object()

    open_calls = []

    def fake_open_ex(*args, **kwargs):
        open_calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(
        "waterlagen.bgt.download.pyogrio.read_info",
        fail_read_info,
    )
    monkeypatch.setattr(
        "waterlagen.bgt.download.gdal.VectorTranslateOptions",
        fake_options,
    )
    monkeypatch.setattr(
        "waterlagen.bgt.download.gdal.VectorTranslate",
        fake_vector_translate,
    )
    monkeypatch.setattr("waterlagen.bgt.download.gdal.OpenEx", fake_open_ex)

    _translate_gml_layer_to_geopackage(
        gml_path,
        tmp_path / "bgt.gpkg",
        layer_name="bgt_waterdeel",
        expected_crs=28992,
        append=False,
        source_crs=28992,
    )

    assert calls[0][2]["options"]["srcSRS"] == "EPSG:28992"
    assert calls[0][2]["options"]["dstSRS"] == "EPSG:28992"
    assert open_calls == [
        (
            (str(gml_path), bgt_download_module.gdal.OF_VECTOR),
            {
                "open_options": [
                    "GML_ATTRIBUTES_TO_OGR_FIELDS=YES",
                    "EXPOSE_GML_ID=YES",
                ]
            },
        )
    ]
    assert calls[0][2]["options"]["layerCreationOptions"] == ["PRECISION=NO"]
    assert calls[0][2]["options"]["transactionSize"] == 100_000


def test_gdal_translation_passes_vsizip_path_to_gdal(monkeypatch, tmp_path):
    gml_path = (
        f"/vsizip/{(tmp_path / 'bgt.zip').resolve().as_posix()}/bgt_waterdeel.gml"
    )
    open_calls = []

    def fail_read_info(*args, **kwargs):
        raise AssertionError("source_crs should skip GML CRS probing")

    def fake_open_ex(*args, **kwargs):
        open_calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(
        "waterlagen.bgt.download.pyogrio.read_info",
        fail_read_info,
    )
    monkeypatch.setattr(
        "waterlagen.bgt.download.gdal.VectorTranslate",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr("waterlagen.bgt.download.gdal.OpenEx", fake_open_ex)

    _translate_gml_layer_to_geopackage(
        gml_path,
        tmp_path / "bgt.gpkg",
        layer_name="bgt_waterdeel",
        expected_crs=28992,
        append=False,
        source_crs=28992,
    )

    assert open_calls[0][0] == (gml_path, bgt_download_module.gdal.OF_VECTOR)
    assert open_calls[0][1] == {
        "open_options": [
            "GML_ATTRIBUTES_TO_OGR_FIELDS=YES",
            "EXPOSE_GML_ID=YES",
        ]
    }


def test_successful_predefined_bgt_download(monkeypatch, tmp_path):
    payload = _zip_with_gml("bgt_waterdeel.gml")
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeStreamResponse(
            payload,
            headers={
                "Content-Length": str(len(payload)),
                "Content-Type": "application/zip",
            },
        )

    monkeypatch.setattr("waterlagen._downloads.requests.get", fake_get)
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": "EPSG:28992"})

    result = download_bgt(download_dir=tmp_path, progress=False)

    assert calls == [
        (
            BGT_PREDEFINED_URL,
            {"stream": True, "allow_redirects": True, "timeout": 30},
        )
    ]
    assert result.source_url == BGT_PREDEFINED_URL
    assert result.archive_path == tmp_path / "bgt-gmllight-nl-nopbp.zip"
    assert result.archive_path.read_bytes() == payload
    assert result.target_path == tmp_path / "bgt.gpkg"
    assert result.downloaded_bytes == len(payload)
    assert result.total_size_known is True
    assert result.layer_count == 1
    assert result.final_crs == "EPSG:28992"
    validate_geopackage(result.target_path)
    assert _temp_files_for(result.target_path) == []
    assert _temp_archives_for(result.archive_path) == []


def test_valid_existing_predefined_archive_is_reused(monkeypatch, tmp_path):
    payload = _zip_with_gml("bgt_waterdeel.gml")
    archive = tmp_path / "bgt-gmllight-nl-nopbp.zip"
    archive.write_bytes(payload)

    def fake_get(url, **kwargs):
        raise AssertionError("valid archive should be reused")

    monkeypatch.setattr("waterlagen._downloads.requests.get", fake_get)
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": "EPSG:28992"})

    result = download_bgt(download_dir=tmp_path, progress=False)

    assert result.archive_path == archive
    assert result.archive_path.read_bytes() == payload
    assert result.downloaded_bytes == 0
    assert result.total_size_known is False
    assert set(pyogrio.list_layers(result.target_path)[:, 0]) == {"bgt_waterdeel"}


def test_corrupt_existing_predefined_archive_is_downloaded_again(
    monkeypatch,
    tmp_path,
):
    payload = _zip_with_gml("bgt_waterdeel.gml")
    archive = tmp_path / "bgt-gmllight-nl-nopbp.zip"
    archive.write_bytes(b"not a zip")
    _mock_download(monkeypatch, FakeStreamResponse(payload))
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": "EPSG:28992"})

    result = download_bgt(download_dir=tmp_path, progress=False)

    assert result.archive_path == archive
    assert result.archive_path.read_bytes() == payload
    assert result.downloaded_bytes == len(payload)
    assert set(pyogrio.list_layers(result.target_path)[:, 0]) == {"bgt_waterdeel"}
    assert _temp_archives_for(result.archive_path) == []


def test_invalid_downloaded_zip_does_not_replace_existing_valid_archive(
    monkeypatch,
    tmp_path,
):
    valid_payload = _zip_with_gml("bgt_waterdeel.gml")
    archive = tmp_path / "bgt-gmllight-nl-nopbp.zip"
    archive.write_bytes(valid_payload)
    _mock_download(monkeypatch, FakeStreamResponse(b"not a zip"))

    with pytest.raises(DownloadPayloadError, match="valid ZIP"):
        bgt_download_module._download_validated_zip_archive(
            url=BGT_PREDEFINED_URL,
            archive_path=archive,
            description=archive.name,
            chunk_size=1024 * 1024,
            timeout=30,
            progress=False,
        )

    assert archive.read_bytes() == valid_payload
    assert _temp_archives_for(archive) == []


def test_predefined_download_with_content_length_reports_progress(
    monkeypatch, tmp_path, capsys
):
    payload = _zip_with_gml("bgt_waterdeel.gml")
    _mock_download(
        monkeypatch,
        FakeStreamResponse(payload, headers={"Content-Length": str(len(payload))}),
    )
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": "EPSG:28992"})

    result = download_bgt(download_dir=tmp_path)

    captured = capsys.readouterr()
    assert result.total_size_known is True
    assert "bgt-gmllight-nl-nopbp.zip" in captured.out
    assert "%" in captured.out


def test_predefined_download_without_content_length_reports_bytes_only(
    monkeypatch, tmp_path, capsys
):
    payload = _zip_with_gml("bgt_waterdeel.gml")
    _mock_download(monkeypatch, FakeStreamResponse(payload))
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": "EPSG:28992"})

    result = download_bgt(download_dir=tmp_path)

    captured = capsys.readouterr()
    assert result.total_size_known is False
    assert "bgt-gmllight-nl-nopbp.zip" in captured.out
    assert "MB" in captured.out
    assert "%" not in captured.out


def test_predefined_download_logs_cache_reading_conversion_and_completion(
    monkeypatch,
    tmp_path,
    caplog,
):
    payload = _zip_with_gml("bgt_waterdeel.gml")
    _mock_download(monkeypatch, FakeStreamResponse(payload))
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": "EPSG:28992"})
    caplog.set_level(logging.INFO, logger="waterlagen.bgt.download")
    caplog.set_level(logging.INFO, logger="waterlagen._downloads")

    download_bgt(download_dir=tmp_path, progress=False)

    assert "bgt-gmllight-nl-nopbp.zip is missing; downloading it" in caplog.text
    assert "Downloading bgt-gmllight-nl-nopbp.zip to" in caplog.text
    assert "Reading BGT archive" in caplog.text
    assert "Reading selected BGT GML bgt_waterdeel.gml" in caplog.text
    assert "Converting bgt_waterdeel.gml to layer bgt_waterdeel" in caplog.text
    assert "Validating final BGT GeoPackage" in caplog.text
    assert "Completed BGT download workflow" in caplog.text


def test_predefined_conversion_uses_vsizip_without_extracting(
    monkeypatch,
    tmp_path,
):
    archive = tmp_path / "bgt-gmllight-nl-nopbp.zip"
    archive.write_bytes(_zip_with_gml("bgt_waterdeel.gml", "nested/bgt_wegdeel.gml"))
    target = tmp_path / "bgt.gpkg"
    calls = []

    def fail_extract(*args, **kwargs):
        raise AssertionError("selected GML files should not be extracted")

    def fake_translate(
        gml_path,
        target_path,
        *,
        layer_name,
        expected_crs,
        append,
        source_crs,
        **kwargs,
    ):
        calls.append((gml_path, target_path, layer_name, expected_crs, append))
        gdf = gpd.GeoDataFrame(
            {"id": [len(calls)]},
            geometry=[Point(100000 + len(calls), 450000)],
            crs=expected_crs,
        )
        pyogrio.write_dataframe(
            gdf,
            target_path,
            layer=layer_name,
            driver="GPKG",
            append=append,
        )

    monkeypatch.setattr("waterlagen.bgt.download.zipfile.ZipFile.extract", fail_extract)
    monkeypatch.setattr(
        "waterlagen.bgt.download._translate_gml_layer_to_geopackage",
        fake_translate,
    )

    layer_count = _convert_bgt_zip_to_geopackage(
        archive,
        target,
        feature_types=["waterdeel", "wegdeel"],
        expected_crs="EPSG:28992",
    )

    assert layer_count == 2
    assert [call[2] for call in calls] == ["bgt_waterdeel", "bgt_wegdeel"]
    assert all(str(call[0]).startswith("/vsizip/") for call in calls)
    assert str(calls[0][0]).endswith("bgt-gmllight-nl-nopbp.zip/bgt_waterdeel.gml")
    assert str(calls[1][0]).endswith("bgt-gmllight-nl-nopbp.zip/nested/bgt_wegdeel.gml")
    assert set(pyogrio.list_layers(target)[:, 0]) == {
        "bgt_waterdeel",
        "bgt_wegdeel",
    }


def test_predefined_conversion_failure_cleans_temporary_geopackage(
    monkeypatch,
    tmp_path,
):
    archive = tmp_path / "bgt-gmllight-nl-nopbp.zip"
    archive.write_bytes(_zip_with_gml("bgt_waterdeel.gml"))
    target = tmp_path / "bgt.gpkg"

    def fake_translate(gml_path, target_path, **kwargs):
        Path(target_path).write_bytes(b"partial geopackage")
        raise DownloadPayloadError("invalid GML data")

    monkeypatch.setattr(
        "waterlagen.bgt.download._translate_gml_layer_to_geopackage",
        fake_translate,
    )

    with pytest.raises(DownloadPayloadError, match="invalid GML data"):
        _convert_bgt_zip_to_geopackage(
            archive,
            target,
            feature_types=["waterdeel"],
            expected_crs="EPSG:28992",
        )

    assert not target.exists()
    assert _temp_files_for(target) == []


def test_predefined_download_logs_reused_valid_archive(
    monkeypatch,
    tmp_path,
    caplog,
):
    archive = tmp_path / "bgt-gmllight-nl-nopbp.zip"
    archive.write_bytes(_zip_with_gml("bgt_waterdeel.gml"))

    def fake_get(url, **kwargs):
        raise AssertionError("valid archive should be reused")

    monkeypatch.setattr("waterlagen._downloads.requests.get", fake_get)
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": "EPSG:28992"})
    caplog.set_level(logging.INFO, logger="waterlagen.bgt.download")

    download_bgt(download_dir=tmp_path, progress=False)

    assert f"Reusing existing valid BGT archive {archive}" in caplog.text


def test_predefined_download_logs_invalid_archive_replacement(
    monkeypatch,
    tmp_path,
    caplog,
):
    archive = tmp_path / "bgt-gmllight-nl-nopbp.zip"
    archive.write_bytes(b"not a zip")
    payload = _zip_with_gml("bgt_waterdeel.gml")
    _mock_download(monkeypatch, FakeStreamResponse(payload))
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": "EPSG:28992"})
    caplog.set_level(logging.INFO, logger="waterlagen.bgt.download")

    download_bgt(download_dir=tmp_path, progress=False)

    assert "is invalid; downloading replacement" in caplog.text
    assert f"Replacing BGT archive {archive}" in caplog.text


def test_invalid_zip_is_rejected(monkeypatch, tmp_path):
    target = tmp_path / "bgt.gpkg"
    existing = _valid_gpkg(target)
    _mock_download(monkeypatch, FakeStreamResponse(b"not a zip"))

    with pytest.raises(DownloadPayloadError, match="valid ZIP"):
        download_bgt(download_dir=tmp_path, progress=False)

    assert target.read_bytes() == existing
    assert _temp_files_for(target) == []


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"<html><body>error</body></html>", "HTML error"),
        (b"<?xml version='1.0'?><error>bad</error>", "XML/HTML error|XML error"),
        (b'{"error": "bad"}', "JSON error"),
    ],
)
def test_error_payloads_are_rejected(monkeypatch, tmp_path, payload, message):
    target = tmp_path / "bgt.gpkg"
    existing = _valid_gpkg(target)
    _mock_download(monkeypatch, FakeStreamResponse(payload))

    with pytest.raises(DownloadPayloadError, match=message):
        download_bgt(download_dir=tmp_path, progress=False)

    assert target.read_bytes() == existing
    assert _temp_files_for(target) == []


def test_interrupted_download_cleans_temp_and_preserves_existing(monkeypatch, tmp_path):
    target = tmp_path / "bgt.gpkg"
    existing = _valid_gpkg(target)
    payload = _zip_with_gml("bgt_waterdeel.gml")
    _mock_download(
        monkeypatch,
        FakeStreamResponse(payload, stream_error=ConnectionError("interrupted")),
    )

    with pytest.raises(ConnectionError, match="interrupted"):
        download_bgt(download_dir=tmp_path, progress=False)

    assert target.read_bytes() == existing
    assert _temp_files_for(target) == []


def test_existing_target_without_overwrite_skips_archive_download(
    monkeypatch,
    tmp_path,
):
    target = tmp_path / "bgt.gpkg"
    existing = _valid_gpkg(target, layer="existing")

    def fake_get(url, **kwargs):
        raise AssertionError("target overwrite=False should skip archive download")

    monkeypatch.setattr("waterlagen._downloads.requests.get", fake_get)

    result = download_bgt(download_dir=tmp_path, overwrite=False, progress=False)

    assert result.target_path == target
    assert result.downloaded_bytes == 0
    assert result.layer_count == 1
    assert target.read_bytes() == existing
    assert not (tmp_path / "bgt-gmllight-nl-nopbp.zip").exists()


def test_multiple_gml_layers_and_layer_names_preserved(monkeypatch, tmp_path):
    payload = _zip_with_gml("bgt_waterdeel.gml", "nested/bgt_wegdeel.gml")
    _mock_download(monkeypatch, FakeStreamResponse(payload))
    _mock_gml_reader(
        monkeypatch,
        {"bgt_waterdeel": "EPSG:28992", "bgt_wegdeel": "EPSG:28992"},
    )

    result = download_bgt(
        download_dir=tmp_path,
        featuretypes=["waterdeel", "wegdeel"],
        progress=False,
    )

    assert result.layer_count == 2
    assert set(pyogrio.list_layers(result.target_path)[:, 0]) == {
        "bgt_waterdeel",
        "bgt_wegdeel",
    }


def test_predefined_download_filters_requested_feature_types(monkeypatch, tmp_path):
    payload = _zip_with_gml(
        "bgt_waterdeel.gml",
        "bgt_pand.gml",
        "bgt_wegdeel.gml",
    )
    _mock_download(monkeypatch, FakeStreamResponse(payload))
    _mock_gml_reader(
        monkeypatch,
        {
            "bgt_waterdeel": "EPSG:28992",
            "bgt_pand": "EPSG:28992",
            "bgt_wegdeel": "EPSG:28992",
        },
    )

    result = download_bgt(
        download_dir=tmp_path,
        featuretypes=["waterdeel", "pand"],
        progress=False,
    )

    assert result.layer_count == 2
    assert set(pyogrio.list_layers(result.target_path)[:, 0]) == {
        "bgt_waterdeel",
        "bgt_pand",
    }


def test_predefined_download_warns_about_missing_feature_types(
    monkeypatch,
    tmp_path,
    caplog,
):
    payload = _zip_with_gml("bgt_waterdeel.gml")
    _mock_download(monkeypatch, FakeStreamResponse(payload))
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": "EPSG:28992"})

    result = download_bgt(
        download_dir=tmp_path,
        featuretypes=["waterdeel", "pand"],
        progress=False,
    )

    assert result.layer_count == 1
    assert "pand (expected bgt_pand.gml)" in caplog.text


def test_layer_already_in_expected_crs(monkeypatch, tmp_path, caplog):
    payload = _zip_with_gml("bgt_waterdeel.gml")
    _mock_download(monkeypatch, FakeStreamResponse(payload))
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": "EPSG:28992"})

    result = download_bgt(download_dir=tmp_path, progress=False)

    assert _spatial_crs_values(result.target_path) == {"bgt_waterdeel": "EPSG:28992"}
    assert "Reprojecting layer" not in caplog.text


def test_layer_in_another_crs_is_reprojected(monkeypatch, tmp_path, caplog):
    payload = _zip_with_gml("bgt_waterdeel.gml")
    _mock_download(monkeypatch, FakeStreamResponse(payload))
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": "EPSG:4326"})

    result = download_bgt(download_dir=tmp_path, progress=False)

    assert _spatial_crs_values(result.target_path) == {"bgt_waterdeel": "EPSG:28992"}
    assert (
        "Layer bgt_waterdeel CRS is EPSG:4326, expected EPSG:28992. Reprojecting layer."
    ) in caplog.text


def test_missing_crs_assigns_expected_crs_with_warning(monkeypatch, tmp_path, caplog):
    payload = _zip_with_gml("bgt_waterdeel.gml")
    _mock_download(monkeypatch, FakeStreamResponse(payload))
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": None})

    result = download_bgt(download_dir=tmp_path, progress=False)

    assert _spatial_crs_values(result.target_path) == {"bgt_waterdeel": "EPSG:28992"}
    assert "Layer bgt_waterdeel has no CRS. Assigning EPSG:28992." in caplog.text


def test_final_geopackage_valid_and_all_layers_expected_crs(monkeypatch, tmp_path):
    payload = _zip_with_gml("bgt_waterdeel.gml", "bgt_wegdeel.gml")
    _mock_download(monkeypatch, FakeStreamResponse(payload))
    _mock_gml_reader(
        monkeypatch,
        {"bgt_waterdeel": "EPSG:4326", "bgt_wegdeel": "EPSG:3857"},
    )

    result = download_bgt(
        download_dir=tmp_path,
        featuretypes=["waterdeel", "wegdeel"],
        progress=False,
    )

    validate_geopackage(result.target_path)
    assert set(_spatial_crs_values(result.target_path).values()) == {"EPSG:28992"}


def test_atomic_replacement_after_success(monkeypatch, tmp_path):
    target = tmp_path / "custom.gpkg"
    _valid_gpkg(target, layer="old")
    payload = _zip_with_gml("bgt_waterdeel.gml")
    _mock_download(monkeypatch, FakeStreamResponse(payload))
    _mock_gml_reader(monkeypatch, {"bgt_waterdeel": "EPSG:28992"})

    result = download_bgt(download_dir=tmp_path, target_path=target, progress=False)

    assert result.target_path == target
    assert set(pyogrio.list_layers(target)[:, 0]) == {"bgt_waterdeel"}
    assert _temp_files_for(target) == []
