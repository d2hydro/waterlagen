"""Extra keuzes moeten door de echte productie-CLI worden begrepen."""

import importlib
import importlib.util
from dataclasses import replace

import geopandas as gpd
import pytest
from shapely.geometry import box
from runscript_test_inputs import make_input
from test_runscript_maken import REPOSITORY, generator


options = importlib.import_module("runscript_tool_tests.waterlagen_options")


@pytest.mark.parametrize(
    ("layer", "flag", "suffix", "error"),
    [
        ("afwateringseenheden", "eigen-hydamo", ".txt", "type .gpkg"),
        ("afwateringseenheden", "eigen-hydamo", ".gpkg", "GeoPackage niet openen"),
        (
            "afwateringseenheden",
            "brandlagen-config",
            ".toml",
            "Ongeldige brandlagen-TOML",
        ),
        ("functioneel_landgebruik", "mapping-csv", ".csv", "Ongeldige codetabel"),
        ("dem", "ahn-vrt", ".vrt", "DTM-VRT niet openen"),
    ],
)
def test_manual_input_with_wrong_type_or_content_is_rejected(
    tmp_path, layer, flag, suffix, error
):
    path = tmp_path / f"invoer{suffix}"
    path.write_text("ongeldig")
    with pytest.raises(ValueError, match=error):
        options.extra_arguments(
            layer, (options.OptionValue(layer, flag, str(path)),), authority=True
        )


@pytest.mark.parametrize(
    ("layer", "flag", "missing"),
    [
        ("afwateringseenheden", "eigen-hydamo", "hydroobject"),
        ("functioneel_landgebruik", "bgt-path", "bgt_waterdeel"),
    ],
)
def test_geopackage_requires_the_right_layers(tmp_path, layer, flag, missing):
    path = tmp_path / "ander.gpkg"
    gpd.GeoDataFrame(geometry=[box(10, 10, 20, 20)], crs=28992).to_file(
        path, layer="niet_de_juiste_laag"
    )
    option = next(item for item in options.EXTRA_OPTIONS[layer] if item.flag == flag)
    with pytest.raises(ValueError, match=f"Ontbrekende lagen:.*{missing}"):
        options.validate_option_path(option, path)


def test_landuse_run_requires_tiles(tmp_path):
    option = next(
        item for item in options.EXTRA_OPTIONS["dem"] if item.flag == "landuse-run"
    )
    with pytest.raises(ValueError, match="leesbaar run.json"):
        options.validate_option_path(option, tmp_path)
    path = make_input(tmp_path, option)
    (path / "tiles/functioneel_landgebruik_test.tif").unlink()
    with pytest.raises(ValueError, match="Geen landgebruikrasters"):
        options.validate_option_path(option, path)


@pytest.mark.parametrize("layer", generator.LAYERS)
def test_all_layer_cli_options_are_available_and_commands_parse(
    layer, tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        f"option_cli_{layer}", REPOSITORY / "scripts" / f"{layer}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parsers = []
    monkeypatch.setattr(
        module, "run_cli", lambda parser, *args, **kwargs: parsers.append(parser)
    )
    module.cli()
    parser = parsers[0]
    common = {
        "help",
        "area",
        "bounds",
        "area-file",
        "area-layer",
        "waterbeheercode",
        "data-dir",
        "datastore",
        "ahn-download-dir",
        "output-root",
        "refresh-sources",
        "offline",
        "debug",
        "workers",
        "run-id",
        "resume",
        "overwrite",
    }
    flags = {
        flag.removeprefix("--")
        for action in parser._actions
        for flag in action.option_strings
        if flag.startswith("--")
    } - common
    assert {option.flag for option in options.EXTRA_OPTIONS[layer]} == flags

    # Exercise the custom VRT here; the fixed version is mutually exclusive.
    tested = [
        option
        for option in options.EXTRA_OPTIONS[layer]
        if option.flag != "ahn-version"
    ]
    choices = []
    for option in tested:
        if option.kind == "boolean":
            value = True
        elif option.kind in {"number", "integer"}:
            value = str(float(option.default or 0) + 1)
            if option.kind == "integer":
                value = str(int(float(value)))
        elif option.kind == "choice":
            value = "average"
        elif option.kind in {"file", "toml", "directory"}:
            value = str(make_input(tmp_path, option))
        else:
            value = "https://example.org/rijkswateren.gpkg"
        choices.append(options.OptionValue(layer, option.flag, value))
    arguments = options.extra_arguments(layer, tuple(choices), authority=True)
    parsed = parser.parse_args(
        [
            "--waterbeheercode",
            "12",
            "--run-id",
            "test",
            *(str(argument) for argument in arguments),
        ]
    )
    assert parsed.waterbeheercode == "12"
    assert all("--" + option.flag in arguments for option in tested)
    commands = generator._commands(
        generator.RunSettings(
            (layer,), ("--waterbeheercode", "12"), "test", extra_options=tuple(choices)
        )
    )
    assert len(commands) == 1
    assert all("--" + option.flag in commands[0] for option in tested)


@pytest.mark.parametrize(
    "flag,value",
    [
        ("building-workers", "0"),
        ("building-workers", "1.5"),
        ("building-percentile", "101"),
        ("building-offset-m", "nan"),
        ("interpolation-max-distance-m", "-1"),
        ("building-buffer-step-m", "0"),
    ],
)
def test_invalid_dem_values_are_rejected_before_saving(flag, value):
    chosen = (options.OptionValue("dem", flag, value),)
    with pytest.raises(ValueError):
        generator._commands(
            generator.RunSettings(
                ("dem",), ("--waterbeheercode", "12"), "test", extra_options=chosen
            )
        )


def test_zero_values_and_layer_specific_flags_are_preserved():
    chosen = (
        options.OptionValue("dem", "building-offset-m", "0"),
        options.OptionValue("dem", "building-workers", "4"),
        options.OptionValue("inwoners", "no-geoparquet", True),
        options.OptionValue("afwateringseenheden", "max-complex-routelengte", "0"),
    )
    settings = generator.RunSettings(
        tuple(generator.LAYERS),
        ("--waterbeheercode", "12"),
        "test",
        extra_options=chosen,
        debug=True,
        overwrite=True,
    )
    landuse, dem, inhabitants, cars, drainage = generator._commands(settings)
    assert "--building-offset-m 0" in dem
    assert "--building-workers 4" in dem
    assert "--no-geoparquet" in inhabitants
    assert "--no-geoparquet" not in cars
    assert "--max-complex-routelengte 0" in drainage
    assert "--building-offset-m" not in landuse
    assert all(
        "--overwrite" in command and "--debug" in command
        for command in generator._commands(settings)
    )
    with pytest.raises(ValueError):
        generator._commands(replace(settings, resume=True))
    with pytest.raises(ValueError):
        generator._commands(replace(settings, refresh_sources=True))


def test_authority_options_require_a_water_authority():
    values = (
        options.OptionValue("afwateringseenheden", "overige-waterschappen", True),
    )
    with pytest.raises(ValueError, match="waterschap"):
        options.extra_arguments("afwateringseenheden", values, authority=False)
