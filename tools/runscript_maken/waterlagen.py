"""Kies een productie en bewaar de opdrachten als aanpasbare runfile."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from waterlagen import areas
from waterlagen._production import validate_run_options, validate_run_target
from waterlagen.areas import Area, area_from_bounds, area_name
from waterlagen.datastore import DataStore

from .script import format_command, start_commands
from .waterlagen_options import HelpText, OptionValue, extra_arguments

LAYERS = {
    "functioneel_landgebruik": "Functioneel landgebruik",
    "dem": "DEM (hoogte)",
    "inwoners": "Inwoners",
    "autos": "Auto's",
    "afwateringseenheden": "Afwateringseenheden",
}
WORKER_LAYERS = {"functioneel_landgebruik", "dem", "afwateringseenheden"}
# Waterbeheercodes uit de HWH-waterschapsgrenzen.
AUTHORITIES = {
    "Aa en Maas": "38",
    "Amstel, Gooi en Vecht": "11",
    "Brabantse Delta": "25",
    "De Dommel": "27",
    "De Stichtse Rijnlanden": "14",
    "Delfland": "15",
    "Drents Overijsselse Delta": "59",
    "Hollands Noorderkwartier (HHNK)": "12",
    "Hollandse Delta": "40",
    "Hunze en Aa's": "33",
    "Limburg": "60",
    "Noorderzijlvest": "34",
    "Rijn en IJssel": "7",
    "Rijnland": "13",
    "Rivierenland": "9",
    "Scheldestromen": "42",
    "Schieland en de Krimpenerwaard": "39",
    "Vallei en Veluwe": "43",
    "Vechtstromen": "44",
    "Wetterskip Fryslân": "2",
    "Zuiderzeeland": "37",
}


LAYER_HELP = {
    "functioneel_landgebruik": HelpText(
        "Maakt een kaart met het gebruik van grond en gebouwen.",
        "functioneel-landgebruik",
        category="bewerkte-lagen",
    ),
    "dem": HelpText(
        "Maakt een hoogtemodel met terreinhoogtes en afgeleide gebouwhoogtes.",
        "dem",
        category="bewerkte-lagen",
    ),
    "inwoners": HelpText(
        "Verdeelt de CBS-inwonersaantallen over woonadressen per buurt.",
        "inwoners",
        category="bewerkte-lagen",
    ),
    "autos": HelpText(
        "Verdeelt de CBS-aantallen personenauto's over woonadressen per buurt.",
        "autos",
        category="bewerkte-lagen",
    ),
    "afwateringseenheden": HelpText(
        "Berekent welke gebieden naar hetzelfde deel van een primaire waterloop afwateren.",
        "afwateringseenheden",
        category="bewerkte-lagen",
    ),
}


@dataclass(frozen=True)
class RunSettings:
    """Keuzes voor één gebied en een of meer producties."""

    layers: tuple[str, ...]
    area_arguments: tuple[str, ...]
    run_id: str
    workers: int = 8
    resume: bool = False
    refresh_sources: bool = False
    brandlagen_config: Path | None = None
    extra_options: tuple[OptionValue, ...] = ()
    overwrite: bool = False
    debug: bool = False


def _scope(arguments: tuple[str, ...]) -> str:
    if len(arguments) in {2, 4} and arguments[0] == "--area-file":
        if not hasattr(areas, "area_from_file"):
            raise ValueError("Deze Waterlagen-versie ondersteunt --area-file nog niet.")
        layer = None
        if len(arguments) == 4:
            if arguments[2] != "--area-layer":
                raise ValueError("Kies een laag met --area-layer.")
            layer = arguments[3]
        return area_name(areas.area_from_file(Path(arguments[1]), layer=layer))
    if len(arguments) == 5 and arguments[0] == "--bounds":
        return area_name(area_from_bounds(arguments[1:]))
    if len(arguments) == 2:
        flag, value = arguments
        if flag == "--waterbeheercode":
            return area_name(",".join(areas.parse_authority_codes(value)))
        if flag == "--area" and value in {area.value for area in Area}:
            return area_name(value)
    raise ValueError(
        "Kies een waterschap, heel Nederland, rechthoek of polygoonbestand."
    )


def _validate(options: RunSettings) -> None:
    if not options.layers or any(layer not in LAYERS for layer in options.layers):
        raise ValueError("Kies minstens één basislaag.")
    _scope(options.area_arguments)
    validate_run_options(
        options.run_id, resume=options.resume, overwrite=options.overwrite
    )
    if (
        options.brandlagen_config is not None
        and "afwateringseenheden" in options.layers
    ):
        from waterlagen.afwateringseenheden.config import read_brandlagen_config

        try:
            read_brandlagen_config(options.brandlagen_config)
        except (ValueError, TypeError, OSError) as error:
            raise ValueError(f"Kan de brandlagen-TOML niet lezen: {error}") from error
    if options.workers < 1:
        raise ValueError("Workers moet minstens 1 zijn.")
    if options.refresh_sources and (options.resume or options.overwrite):
        raise ValueError("Bronnen opnieuw ophalen vereist een nieuwe run.")
    for layer in options.layers:
        extra_arguments(
            layer,
            options.extra_options,
            authority=options.area_arguments[0] == "--waterbeheercode",
        )


def _existing_layers(options: RunSettings) -> tuple[str, ...]:
    """Zoek alleen bij de geselecteerde lagen en het gekozen gebied."""
    validate_run_options(options.run_id, resume=False, overwrite=False)
    scope = _scope(options.area_arguments)
    store = DataStore()
    return tuple(
        layer
        for layer in options.layers
        if (store.processed_data_dir / layer / scope / options.run_id).exists()
    )


def _window_commands(options: RunSettings) -> list[str]:
    """Hervat of vervang bestaande lagen; ontbrekende lagen beginnen nieuw."""
    existing = _existing_layers(options)
    store = DataStore()
    scope = _scope(options.area_arguments)
    commands = []
    for layer in options.layers:
        present = layer in existing
        target = store.processed_data_dir / layer / scope / options.run_id
        if present and not (target / "run.json").is_file():
            raise ValueError(
                f"De map voor {LAYERS[layer]} bestaat, maar bevat geen run.json. "
                "Kies een nieuwe runnaam."
            )
        if present and not (options.resume or options.overwrite):
            raise ValueError(
                "Deze run bestaat al. Kies hervatten of opnieuw berekenen."
            )
        commands.extend(
            _commands(
                replace(
                    options,
                    layers=(layer,),
                    resume=present and options.resume,
                    overwrite=present and options.overwrite,
                )
            )
        )
    if not commands:
        raise ValueError("Kies minstens één basislaag.")
    return commands


def _start_code_update(project: Path) -> subprocess.Popen:
    """Start de bestaande updater buiten de actieve productieomgeving."""
    launcher = project / (
        "code_bijwerken.bat" if sys.platform == "win32" else "code_bijwerken.sh"
    )
    if not launcher.is_file():
        raise ValueError("Code bijwerken is beschikbaar in de uitgepakte productiemap.")
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith("CONDA_") or name in {
            "PIXI_ENVIRONMENT_NAME",
            "PIXI_ENVIRONMENT_PLATFORMS",
            "PIXI_IN_SHELL",
            "PIXI_PROJECT_MANIFEST",
            "PIXI_PROJECT_ROOT",
            "PIXI_PROJECT_NAME",
            "PIXI_PROJECT_VERSION",
            "PIXI_PROMPT",
            "GDAL_DATA",
            "GDAL_DRIVER_PATH",
            "PROJ_DATA",
        }:
            environment.pop(name)
        elif name.upper() in {"SSL_CERT_DIR", "SSL_CERT_FILE"} and re.search(
            r"\.pixi[\\/]envs[\\/]", environment[name], re.IGNORECASE
        ):
            environment.pop(name)
        elif name.upper() == "PATH":
            environment[name] = os.pathsep.join(
                part
                for part in environment[name].split(os.pathsep)
                if not re.search(r"\.pixi[\\/]envs[\\/]", part, re.IGNORECASE)
            )
    arguments = [launcher] if sys.platform == "win32" else ["sh", launcher]
    return start_commands(format_command(arguments), project, env=environment)


def _layer_flags(layer: str, options: RunSettings, *, resume: bool) -> list[str | Path]:
    """Gebruik dezelfde productieopties voor een opgeslagen script en een directe start."""
    arguments: list[str | Path] = []
    if layer in WORKER_LAYERS:
        arguments.extend(["--workers", str(options.workers)])
    if resume:
        arguments.append("--resume")
    if options.refresh_sources:
        arguments.append("--refresh-sources")
    if options.overwrite:
        arguments.append("--overwrite")
    if options.debug:
        arguments.append("--debug")
    if layer == "afwateringseenheden" and options.brandlagen_config is not None:
        arguments.extend(["--brandlagen-config", options.brandlagen_config.resolve()])
    arguments.extend(
        extra_arguments(
            layer,
            options.extra_options,
            authority=options.area_arguments[0] == "--waterbeheercode",
        )
    )
    return arguments


def _commands(options: RunSettings) -> list[str]:
    """Maak één direct aanpasbaar Pixi-commando per laag."""
    _validate(options)
    area_arguments: list[str | Path] = list(options.area_arguments)
    if area_arguments[0] == "--bounds":
        area_arguments = [
            "--bounds",
            *(str(float(value)) for value in options.area_arguments[1:]),
        ]
    elif area_arguments[0] == "--area-file":
        area_arguments[1] = Path(options.area_arguments[1]).resolve()
    commands = []
    for layer in options.layers:
        arguments = [
            "pixi",
            "run",
            "--locked",
            layer,
            *area_arguments,
            "--run-id",
            options.run_id,
        ]
        arguments.extend(_layer_flags(layer, options, resume=options.resume))
        commands.append(format_command(arguments))
    return commands


def _start(options: RunSettings, project: Path) -> int:
    """Hervat alleen bestaande runs; de bestaande CLI bewaakt compatibiliteit."""
    _validate(options)
    scope = _scope(options.area_arguments)
    store = DataStore()
    for layer in options.layers:
        target = store.processed_data_dir / layer / scope / options.run_id
        resume = options.resume and target.exists()
        validate_run_target(
            store.processed_data_dir,
            layer,
            scope,
            options.run_id,
            resume=resume,
            overwrite=options.overwrite,
        )
        command = [
            sys.executable,
            str(project / "scripts" / f"{layer}.py"),
            *options.area_arguments,
            "--run-id",
            options.run_id,
        ]
        command.extend(
            str(flag) for flag in _layer_flags(layer, options, resume=resume)
        )
        action = "Nieuwe run"
        if resume:
            action = "Hervatten"
        elif options.overwrite:
            action = "Overschrijven"
        print(f"{action}: {LAYERS[layer]} ({options.run_id})", flush=True)
        result = subprocess.run(command, cwd=project, check=False)
        if result.returncode:
            return result.returncode
    return 0


def main() -> int:
    """Open het keuzevenster of start één laag vanuit een opgeslagen script."""
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--start", choices=LAYERS)
    parser.add_argument("--run-id")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--refresh-sources", action="store_true")
    parser.add_argument("--brandlagen-config", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--waterbeheercode")
    group.add_argument("--area", choices=[area.value for area in Area])
    group.add_argument("--bounds", nargs=4)
    group.add_argument("--area-file", type=Path)
    parser.add_argument("--area-layer")
    args = parser.parse_args()
    project = Path.cwd()
    if not (project / "pixi.toml").is_file():
        parser.error("Start vanuit de projectmap waar pixi.toml staat.")
    if not args.start:
        from .browser_server import open_browser

        open_browser(project)
        return 0
    if not args.run_id:
        parser.error("Geef een runnaam op met --run-id.")
    if args.area_layer and args.area_file is None:
        parser.error("--area-layer vereist --area-file.")
    if args.area_file is not None:
        area_arguments = ("--area-file", str(args.area_file))
        if args.area_layer is not None:
            area_arguments += ("--area-layer", args.area_layer)
    elif args.bounds:
        area_arguments = ("--bounds", *args.bounds)
    elif args.waterbeheercode:
        area_arguments = ("--waterbeheercode", args.waterbeheercode)
    else:
        area_arguments = ("--area", args.area or "nederland")
    try:
        return _start(
            RunSettings(
                (args.start,),
                area_arguments,
                args.run_id,
                args.workers,
                args.resume,
                args.refresh_sources,
                args.brandlagen_config,
                overwrite=args.overwrite,
                debug=args.debug,
            ),
            project,
        )
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
