"""Bestaande runfiles lezen en opnieuw gebruiken zonder ze uit te voeren."""

import importlib
import shutil
import subprocess

import geopandas as gpd
import pytest
from shapely.geometry import box
from runscript_test_inputs import make_input
from waterlagen.functioneel_landgebruik.landgebruikstabel import DEFAULT_MAPPING_CSV
from test_runscript_maken import generator, script_helpers

runfiles = importlib.import_module("runscript_tool_tests.waterlagen_runfile")
options_module = importlib.import_module("runscript_tool_tests.waterlagen_options")


def read(tmp_path, script):
    path = tmp_path / "run.ps1"
    path.write_text(script, encoding="utf-8-sig")
    return runfiles.read_runfile(path, tmp_path)


@pytest.mark.parametrize("extension", [".ps1", ".bat"])
@pytest.mark.parametrize("height_source", ["ahn-version", "ahn-vrt"])
def test_all_selected_options_survive_saving_and_loading(tmp_path, extension, height_source):
    choices = []
    for layer, options in options_module.EXTRA_OPTIONS.items():
        for option in options:
            if option.flag in {"ahn-version", "ahn-vrt"} and option.flag != height_source:
                continue
            value = option.default
            if option.kind == "boolean":
                value = True
            elif option.kind in {"file", "directory", "toml"}:
                value = str(make_input(tmp_path, option))
            elif option.kind == "choice":
                value = "6" if option.flag == "ahn-version" else "average"
            choices.append(options_module.OptionValue(layer, option.flag, value))
    original = generator.RunSettings(
        tuple(generator.LAYERS),
        ("--waterbeheercode", "38"),
        "aa-en-maas-proef",
        32,
        overwrite=True,
        debug=True,
        extra_options=tuple(choices),
    )
    commands = generator._commands(original)
    path = tmp_path / ("run" + extension)
    content = (
        script_helpers.build_batch_script(commands, tmp_path, path)
        if extension == ".bat"
        else script_helpers.build_script(commands)
    )
    script_helpers.save_script(content, path, tmp_path)
    loaded = runfiles.read_runfile(path, tmp_path)
    assert generator._commands(loaded) == commands
    assert loaded.workers == 32
    assert loaded.overwrite and loaded.debug


@pytest.mark.parametrize(
    "area", [("--area", "nederland"), ("--bounds", "1", "2", "3", "4")]
)
def test_area_and_layer_selection_round_trip(tmp_path, area):
    original = generator.RunSettings(("dem", "inwoners"), area, "proef", resume=True)
    commands = generator._commands(original)
    assert generator._commands(read(tmp_path, "\n".join(commands))) == commands


def test_polygon_paths_with_quotes_and_shell_characters_are_read_literally(tmp_path):
    polygon = tmp_path / "Aa's $gebied `test`.gpkg"
    gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs=28992).to_file(
        polygon, layer="gebied"
    )
    original = generator.RunSettings(
        ("dem",), ("--area-file", str(polygon), "--area-layer", "gebied"), "proef"
    )
    commands = generator._commands(original)
    assert generator._commands(read(tmp_path, "\n".join(commands))) == commands


def test_plain_commands_comments_and_multiline_are_supported(tmp_path):
    loaded = read(
        tmp_path,
        '# Mijn run\npixi run --locked dem `\n --waterbeheercode 12 --run-id "proef" --workers 8 # uitleg\n',
    )
    assert loaded.run_id == "proef"
    assert loaded.layers == ("dem",)


def test_relative_source_paths_use_the_production_project(tmp_path):
    shutil.copyfile(DEFAULT_MAPPING_CSV, tmp_path / "mapping.csv")
    loaded = read(
        tmp_path,
        "pixi run --locked functioneel_landgebruik --run-id proef --mapping-csv mapping.csv",
    )
    assert loaded.extra_options[0].value == str(tmp_path / "mapping.csv")


@pytest.mark.parametrize(
    "script, message",
    [
        ("", "geen pixi"),
        ("Remove-Item test", "alleen pixi"),
        ("pixi run --locked dem --run-id proef; Remove-Item test", "alleen pixi"),
        ('pixi run --locked dem --run-id "$naam"', "alleen pixi"),
        ("pixi run --locked dem --run-id proef --unknown 1", "niet ondersteund"),
        ("pixi run --locked dem --run-id proef --run-id dubbel", "dubbel"),
        ("pixi run --locked dem --run-id", "waarde"),
        ("pixi run --locked dem --workers nope --run-id proef", "geheel getal"),
        ("pixi run --locked dem --run-id proef --resume --overwrite", "resume"),
        ("pixi run --locked dem --area alkmaar --run-id proef", "waterschap"),
        (
            "pixi run --locked dem --waterbeheercode 999 --run-id proef",
            "waterbeheercode",
        ),
        (
            "pixi run --locked dem --run-id proef\npixi run --locked inwoners --run-id ander",
            "dezelfde runnaam",
        ),
        (
            "pixi run --locked functioneel_landgebruik --workers 4 --run-id proef\npixi run --locked dem --workers 8 --run-id proef",
            "hetzelfde aantal workers",
        ),
    ],
)
def test_unrepresentable_scripts_are_rejected_without_execution(
    tmp_path, monkeypatch, script, message
):
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("Inladen mag niets starten"),
    )
    with pytest.raises(ValueError, match=message):
        read(tmp_path, script)


def test_code_update_uses_existing_launcher_and_clean_environment(
    tmp_path, monkeypatch
):
    name = (
        "code_bijwerken.bat"
        if generator.sys.platform == "win32"
        else "code_bijwerken.sh"
    )
    (tmp_path / name).write_text("test")
    monkeypatch.setenv("CONDA_PREFIX", str(tmp_path / ".pixi/envs/default"))
    monkeypatch.setenv("PIXI_IN_SHELL", "1")
    monkeypatch.setenv(
        "PATH",
        generator.os.pathsep.join(
            [str(tmp_path / ".pixi/envs/default"), "keep-pixi-path"]
        ),
    )
    monkeypatch.setenv("DATA_DIR", "keep-data")
    calls = []
    monkeypatch.setattr(
        generator,
        "start_commands",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    generator._start_code_update(tmp_path)
    command = calls[0][0][0]
    env = calls[0][1]["env"]
    assert name in command
    assert "--yes" not in command
    assert "CONDA_PREFIX" not in env
    assert "PIXI_IN_SHELL" not in env
    assert env["PATH"] == "keep-pixi-path"
    assert env["DATA_DIR"] == "keep-data"


@pytest.mark.parametrize("extension", [".bat", ".ps1"])
def test_multiple_authorities_survive_saving_and_loading(tmp_path, extension):
    original = generator.RunSettings(
        tuple(generator.LAYERS), ("--waterbeheercode", "12,13"), "samen"
    )
    commands = generator._commands(original)
    text = (
        script_helpers.build_batch_script(commands, tmp_path)
        if extension == ".bat"
        else script_helpers.build_script(commands)
    )
    path = tmp_path / ("samen" + extension)
    script_helpers.save_script(text, path, project=tmp_path)
    loaded = runfiles.read_runfile(path, tmp_path)
    assert loaded == original
    assert generator._scope(loaded.area_arguments) == "waterschappen_12_13"
    assert len(commands) == 5
