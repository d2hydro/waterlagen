import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_landgebruik_script():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "functioneel_landgebruik.py"
    )
    spec = importlib.util.spec_from_file_location("landgebruik_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("configured_default", [False, True])
@pytest.mark.parametrize("prepared_bgt", [False, True])
@pytest.mark.parametrize("missing_bgt", [False, True])
def test_landgebruik_script_builds_tiles_vrt_and_cog_in_order(
    tmp_path,
    monkeypatch,
    capsys,
    configured_default,
    prepared_bgt,
    missing_bgt,
):
    landgebruik = _load_landgebruik_script()
    events = []
    processed_dir = tmp_path / "processed"
    data_dir_root = tmp_path / "data"
    tiles_path = processed_dir / landgebruik.UITVOERMAP / "tiles.gpkg"
    tile_files = [
        processed_dir / "functioneel_landgebruik" / "tiles" / "tile-a.tif",
        processed_dir / "functioneel_landgebruik" / "tiles" / "tile-b.tif",
    ]

    def fake_build_tiles(**kwargs):
        events.append(("build_tiles", kwargs))
        return tiles_path

    def fake_build_landgebruik_tiles(**kwargs):
        events.append(("build_landgebruik_tiles", kwargs))
        return tile_files

    def fake_create_vrt_file(**kwargs):
        events.append(("create_vrt_file", kwargs))
        return kwargs["vrt_file"]

    def fake_create_cog_file(**kwargs):
        events.append(("create_cog_file", kwargs))
        return kwargs["cog_file"]

    data_store = SimpleNamespace(
        data_dir=data_dir_root,
        processed_data_dir=processed_dir,
        source_data_dir=tmp_path / "source",
        bgt_dir=tmp_path / "source/bgt",
        bag_dir=tmp_path / "source/bag",
        brp_dir=tmp_path / "source/brp",
        top10nl_dir=tmp_path / "source/top10nl",
        dijkringen_dir=tmp_path / "source/dijkringen",
    )
    monkeypatch.setattr(landgebruik, "WORKERS", 2)
    monkeypatch.setattr(landgebruik, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        landgebruik.pyogrio,
        "read_info",
        lambda *args, **kwargs: {
            "features": 2,
            "fields": ["bgt-status", "eindRegistratie", "objectEindTijd"],
        },
    )
    monkeypatch.setattr(landgebruik, "build_tiles", fake_build_tiles)
    monkeypatch.setattr(
        landgebruik,
        "bouw_functioneel_landgebruik_tiles",
        fake_build_landgebruik_tiles,
    )
    monkeypatch.setattr(landgebruik, "create_vrt_file", fake_create_vrt_file)
    monkeypatch.setattr(landgebruik, "create_cog_file", fake_create_cog_file)

    default_bgt = data_store.bgt_dir / landgebruik.BGT_BESTAND
    default_bgt.parent.mkdir(parents=True)
    default_bgt.touch()
    bgt_path = None
    if prepared_bgt:
        bgt_path = tmp_path / "actuele_bgt.gpkg"
        bgt_path.touch()
    if missing_bgt:
        (bgt_path or default_bgt).unlink()
        with pytest.raises(FileNotFoundError, match="bgt_actuele_vlakken.py"):
            landgebruik.main(data_store=data_store, bgt_path=bgt_path)
        assert [event for event, _kwargs in events] == ["build_tiles"]
        return
    if configured_default:
        monkeypatch.chdir(tmp_path)
        for name in ("DATA_DIR", "SOURCE_DATA_DIR", "PROCESSED_DATA_DIR"):
            monkeypatch.delenv(name, raising=False)
        (tmp_path / ".datastore").write_text(
            f"DATA_DIR={data_dir_root.as_posix()}\n"
            f"SOURCE_DATA_DIR={(tmp_path / 'source').as_posix()}\n"
            f"PROCESSED_DATA_DIR={processed_dir.as_posix()}\n",
            encoding="utf-8",
        )
        result = landgebruik.main(bgt_path=bgt_path)
    else:
        result = landgebruik.main(data_store=data_store, bgt_path=bgt_path)

    data_dir = processed_dir / landgebruik.UITVOERMAP
    tiles_dir = data_dir / "tiles"
    vrt_file = data_dir / "functioneel_landgebruik.vrt"
    cog_file = data_dir / "functioneel_landgebruik.tif"

    assert [event for event, _kwargs in events] == [
        "build_tiles",
        "build_landgebruik_tiles",
        "create_vrt_file",
        "create_cog_file",
    ]
    assert events[0][1] == {
        "target_path": tiles_path,
        "tile_size_m": 5000,
        "overwrite": False,
    }
    assert events[1][1]["target_dir"] == tiles_dir
    assert events[1][1]["tiles_path"] == tiles_path
    assert events[1][1]["workers"] == 2
    assert events[1][1]["sources"].bgt_gpkg == (
        bgt_path or tmp_path / "source/bgt" / landgebruik.BGT_BESTAND
    )
    assert events[1][1]["overwrite"] is True
    assert events[1][1]["diagnostics_path"] == data_dir / "nodata.gpkg"
    assert events[1][1]["download_missing_sources"] is False
    assert events[2][1] == {"vrt_file": vrt_file, "directory": tiles_dir}
    assert events[3][1] == {
        "vrt_file": vrt_file,
        "cog_file": cog_file,
        "overwrite": False,
    }
    assert result == cog_file
    assert cog_file.with_suffix(".qml").is_file()

    assert capsys.readouterr().out == ""
    import json

    status = json.loads((data_dir / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "Voltooid"
    assert status["completed_tiles"] == 2
    assert (
        data_dir / "landgebruik_met_code.csv"
    ).read_bytes() == landgebruik.LANDGEBRUIK_CSV.read_bytes()
