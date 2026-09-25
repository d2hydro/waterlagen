"""Production folders never silently mix runs, settings or input versions."""

import json
import re

import pytest

from waterlagen import _production
from waterlagen._production import production_run


def test_timestamp_scope_and_metadata(tmp_path):
    with production_run(
        tmp_path, "autos", "nederland", parameters={"year": 2025}
    ) as run:
        assert run.path.parent == tmp_path / "autos" / "nederland"
        assert re.fullmatch(r"\d{8}T\d{6}Z", run.path.name)
        run.record_inputs({"optional": None})
        assert (run.path / ".run.lock").exists()
    metadata = json.loads((run.path / "run.json").read_text())
    assert metadata["status"] == "complete"
    assert metadata["parameters"] == {"year": 2025}
    assert metadata["software_version"]
    assert metadata["inputs"] == {"optional": None}
    assert not (run.path / ".run.lock").exists()


@pytest.mark.parametrize(
    "name", ["", "../outside", "a/b", "a\\b", "C:run", "CON", "nul", "a b", "a" * 101]
)
def test_invalid_run_names(tmp_path, name):
    with (
        pytest.raises(ValueError, match="Run-ID"),
        production_run(tmp_path, "autos", "nederland", run_id=name, parameters={}),
    ):
        pytest.fail("Invalid name accepted")
    assert not list(tmp_path.iterdir())


def test_new_run_collision_and_explicit_reuse(tmp_path, monkeypatch):
    monkeypatch.setattr(_production, "default_run_id", lambda: "20260925T120000Z")
    with production_run(tmp_path, "autos", "nederland", parameters={}) as run:
        (run.path / "autos.gpkg").write_bytes(b"keep")
    with (
        pytest.raises(ValueError, match="bestaat al"),
        production_run(tmp_path, "autos", "nederland", parameters={}),
    ):
        pytest.fail("Collision accepted")
    for mode in ("resume", "overwrite"):
        with production_run(
            tmp_path,
            "autos",
            "nederland",
            run_id=run.path.name,
            parameters={},
            **{mode: True},
        ) as reused:
            assert reused.path == run.path
            assert reused.metadata["mode"] == mode
            assert (run.path / "autos.gpkg").read_bytes() == b"keep"


@pytest.mark.parametrize(
    "options",
    [
        {"resume": True},
        {"overwrite": True},
        {"run_id": "test", "resume": True, "overwrite": True},
    ],
)
def test_reuse_requires_explicit_unambiguous_options(tmp_path, options):
    with (
        pytest.raises(ValueError),
        production_run(tmp_path, "autos", "nederland", parameters={}, **options),
    ):
        pytest.fail("Invalid options accepted")


def test_legacy_folder_is_not_adopted(tmp_path):
    path = tmp_path / "autos" / "nederland" / "test"
    path.mkdir(parents=True)
    (path / "autos.gpkg").write_bytes(b"legacy")
    with (
        pytest.raises(ValueError, match="geen run.json"),
        production_run(
            tmp_path, "autos", "nederland", run_id="test", resume=True, parameters={}
        ),
    ):
        pytest.fail("Legacy folder adopted")
    assert not (path / "run.json").exists()


@pytest.mark.parametrize("mode", ["resume", "overwrite"])
def test_parameter_and_software_mismatch_preserve_run(tmp_path, monkeypatch, mode):
    with production_run(
        tmp_path, "autos", "nederland", run_id="test", parameters={"year": 2025}
    ) as run:
        pass
    original = (run.path / "run.json").read_bytes()
    with (
        pytest.raises(ValueError, match="andere instellingen"),
        production_run(
            tmp_path,
            "autos",
            "nederland",
            run_id="test",
            parameters={"year": 2026},
            **{mode: True},
        ),
    ):
        pytest.fail("Changed parameters accepted")
    monkeypatch.setattr(_production, "version", lambda name: "different-version")
    with (
        pytest.raises(ValueError, match="software"),
        production_run(
            tmp_path,
            "autos",
            "nederland",
            run_id="test",
            parameters={"year": 2025},
            **{mode: True},
        ),
    ):
        pytest.fail("Changed software accepted")
    assert (run.path / "run.json").read_bytes() == original


def test_changed_inputs_stop_before_output_reuse(tmp_path):
    source = tmp_path / "source.gpkg"
    source.write_bytes(b"original")
    with production_run(
        tmp_path, "autos", "nederland", run_id="test", parameters={}
    ) as run:
        run.record_inputs({"source": source})
    source.write_bytes(b"changed source")
    with (
        pytest.raises(ValueError, match="andere bronbestanden"),
        production_run(
            tmp_path, "autos", "nederland", run_id="test", resume=True, parameters={}
        ) as run,
    ):
        run.record_inputs({"source": source})
        pytest.fail("Changed inputs accepted")
    assert json.loads((run.path / "run.json").read_text())["status"] == "failed"
    assert not (run.path / ".run.lock").exists()


def test_vrt_tracks_dependencies_without_false_mtime_conflicts(tmp_path):
    source = tmp_path / "tile.tif"
    source.write_bytes(b"raster")
    vrt = tmp_path / "input.vrt"
    content = '<VRTDataset><VRTRasterBand><SimpleSource><SourceFilename relativeToVRT="1">tile.tif</SourceFilename></SimpleSource></VRTRasterBand></VRTDataset>'
    vrt.write_text(content)
    with production_run(
        tmp_path, "afwateringseenheden", "waterschap_38", run_id="test", parameters={}
    ) as run:
        run.record_inputs({"ahn": vrt})
    vrt.write_text(content)
    with production_run(
        tmp_path,
        "afwateringseenheden",
        "waterschap_38",
        run_id="test",
        resume=True,
        parameters={},
    ) as run:
        run.record_inputs({"ahn": vrt})
    source.write_bytes(b"changed raster")
    with (
        pytest.raises(ValueError, match="andere bronbestanden"),
        production_run(
            tmp_path,
            "afwateringseenheden",
            "waterschap_38",
            run_id="test",
            resume=True,
            parameters={},
        ) as run,
    ):
        run.record_inputs({"ahn": vrt})


def test_failure_can_be_resumed_but_active_run_cannot(tmp_path):
    with (
        pytest.raises(RuntimeError, match="interrupted"),
        production_run(
            tmp_path, "autos", "nederland", run_id="test", parameters={}
        ) as run,
    ):
        with (
            pytest.raises(ValueError, match="vergrendeld"),
            production_run(
                tmp_path,
                "autos",
                "nederland",
                run_id="test",
                resume=True,
                parameters={},
            ),
        ):
            pytest.fail("Concurrent run accepted")
        raise RuntimeError("interrupted")
    assert json.loads((run.path / "run.json").read_text())["error"] == "interrupted"
    with production_run(
        tmp_path, "autos", "nederland", run_id="test", resume=True, parameters={}
    ):
        pass
    metadata = json.loads((run.path / "run.json").read_text())
    assert metadata["status"] == "complete"
    assert "error" not in metadata
