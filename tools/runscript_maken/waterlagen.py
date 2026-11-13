"""Kies een productie en bewaar de opdrachten als aanpasbaar PowerShell-script."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from waterlagen import areas
from waterlagen._production import validate_run_options, validate_run_target
from waterlagen.areas import Area, area_from_bounds, area_name
from waterlagen.datastore import DataStore
from waterlagen.settings import settings

from .script import ScriptPlan, format_command
from .window import open_window

if TYPE_CHECKING:
    from tkinter import ttk

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


@dataclass(frozen=True)
class RunSettings:
    """Keuzes voor één gebied en een of meer producties."""

    layers: tuple[str, ...]
    area_arguments: tuple[str, ...]
    run_id: str
    workers: int = 8
    resume: bool = False
    refresh_sources: bool = False


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
        if flag == "--waterbeheercode" and value.isascii() and value.isdigit():
            return area_name(value)
        if flag == "--area" and value in {area.value for area in Area}:
            return area_name(value)
    raise ValueError(
        "Kies een waterschap, heel Nederland, rechthoek of polygoonbestand."
    )


def _validate(options: RunSettings) -> None:
    if not options.layers or any(layer not in LAYERS for layer in options.layers):
        raise ValueError("Kies minstens één basislaag.")
    _scope(options.area_arguments)
    validate_run_options(options.run_id, resume=options.resume, overwrite=False)
    if options.workers < 1:
        raise ValueError("Workers moet minstens 1 zijn.")
    if options.resume and options.refresh_sources:
        raise ValueError("Bronnen opnieuw ophalen kan niet samen met hervatten.")


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
        if layer in WORKER_LAYERS:
            arguments.extend(["--workers", str(options.workers)])
        if options.resume:
            arguments.append("--resume")
        if options.refresh_sources:
            arguments.append("--refresh-sources")
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
            overwrite=False,
        )
        command = [
            sys.executable,
            str(project / "scripts" / f"{layer}.py"),
            *options.area_arguments,
            "--run-id",
            options.run_id,
        ]
        if layer in WORKER_LAYERS:
            command.extend(["--workers", str(options.workers)])
        if resume:
            command.append("--resume")
        if options.refresh_sources:
            command.append("--refresh-sources")
        action = "Hervatten" if resume else "Nieuwe run"
        print(f"{action}: {LAYERS[layer]} ({options.run_id})", flush=True)
        result = subprocess.run(command, cwd=project, check=False)
        if result.returncode:
            return result.returncode
    return 0


def _build_form(frame: ttk.Frame) -> Callable[[], ScriptPlan]:
    """Vul het venster met Waterlagen-keuzes; lees ze pas bij bekijken of opslaan."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = frame.winfo_toplevel()
    ttk.Label(frame, text="1. Gebied", style="Heading.TLabel").pack(anchor="w")
    mode = tk.StringVar(value="waterschap")
    modes = ttk.Frame(frame)
    modes.pack(fill="x", pady=8)
    selection = ttk.Frame(frame)
    authority = tk.StringVar(value="Hollands Noorderkwartier (HHNK)")
    authority_input = ttk.Combobox(
        selection, textvariable=authority, values=list(AUTHORITIES), state="readonly"
    )
    national_hint = ttk.Label(
        selection,
        text="De gekozen lagen worden voor heel Nederland gemaakt.",
        style="Hint.TLabel",
    )
    bounds_frame = ttk.Frame(selection)
    bounds = [tk.StringVar() for _ in range(4)]
    for index, (label, value) in enumerate(
        zip(("X min", "Y min", "X max", "Y max"), bounds)
    ):
        ttk.Label(bounds_frame, text=label).grid(row=0, column=index, sticky="w")
        ttk.Entry(bounds_frame, textvariable=value, width=13).grid(
            row=1, column=index, padx=(0, 10)
        )
    ttk.Label(
        bounds_frame,
        text=f"Coördinaten in {settings.crs}; gebruik een punt voor decimalen.",
        style="Hint.TLabel",
    ).grid(row=2, column=0, columnspan=4, sticky="w", pady=4)

    polygon_frame = ttk.Frame(selection)
    polygon_frame.columnconfigure(0, weight=1)
    polygon_path = tk.StringVar()
    polygon_layer = tk.StringVar()
    ttk.Entry(polygon_frame, textvariable=polygon_path, state="readonly").grid(
        row=0, column=0, sticky="ew", padx=(0, 8)
    )
    layer_row = ttk.Frame(polygon_frame)
    layer_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    ttk.Label(layer_row, text="Laag").pack(side="left", padx=(0, 8))
    layer_input = ttk.Combobox(layer_row, textvariable=polygon_layer, state="readonly")
    layer_input.pack(side="left", fill="x", expand=True)
    ttk.Label(
        polygon_frame,
        text="Alle polygonen in deze laag vormen samen het gebied.",
        style="Hint.TLabel",
    ).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)

    def choose_polygon() -> None:
        filename = filedialog.askopenfilename(
            parent=root,
            title="Polygoonbestand kiezen",
            filetypes=[("GeoPackage of GeoJSON", "*.gpkg *.geojson *.json")],
        )
        if not filename:
            return
        try:
            names = areas.area_file_layers(Path(filename))
        except ValueError as error:
            messagebox.showerror(
                "Polygoonbestand niet bruikbaar", str(error), parent=root
            )
            return
        polygon_path.set(str(Path(filename).resolve()))
        layer_input.configure(values=names)
        polygon_layer.set(names[0] if len(names) == 1 else "")

    choose_button = ttk.Button(
        polygon_frame, text="Bestand kiezen", command=choose_polygon
    )
    choose_button.grid(row=0, column=1)
    if not hasattr(areas, "area_from_file"):
        choose_button.state(["disabled"])
        ttk.Label(
            polygon_frame,
            text="De geïnstalleerde versie ondersteunt polygoonbestanden nog niet.",
            style="Hint.TLabel",
        ).grid(row=3, column=0, columnspan=2, sticky="w")

    def show_area() -> None:
        for child in selection.winfo_children():
            child.pack_forget()
        widgets = {
            "waterschap": authority_input,
            "nederland": national_hint,
            "bounds": bounds_frame,
            "polygoon": polygon_frame,
        }
        widgets[mode.get()].pack(fill="x")

    for label, value in (
        ("Waterschap", "waterschap"),
        ("Heel Nederland", "nederland"),
        ("Eigen rechthoek", "bounds"),
        ("Polygoonbestand", "polygoon"),
    ):
        ttk.Radiobutton(
            modes, text=label, variable=mode, value=value, command=show_area
        ).pack(side="left", padx=(0, 16))
    selection.pack(fill="x")
    show_area()
    ttk.Label(
        frame,
        text="De gebiedsgrens selecteert de invoer; de uitvoer kan daarbuiten liggen.",
        style="Hint.TLabel",
    ).pack(anchor="w", pady=(8, 18))

    ttk.Label(frame, text="2. Basislagen", style="Heading.TLabel").pack(anchor="w")
    layers = {}
    for layer, label in LAYERS.items():
        layers[layer] = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text=label, variable=layers[layer]).pack(
            anchor="w", pady=3
        )

    ttk.Label(frame, text="3. Uitvoering", style="Heading.TLabel").pack(
        anchor="w", pady=(18, 8)
    )
    execution = ttk.Frame(frame)
    execution.pack(fill="x")
    execution.columnconfigure(0, weight=1)
    run_id = tk.StringVar(
        value=datetime.now(UTC).astimezone().strftime("proef-%Y%m%d-%H%M%S")
    )
    workers = tk.StringVar(value="8")
    ttk.Label(execution, text="Runnaam").grid(row=0, column=0, sticky="w")
    ttk.Label(execution, text="Workers").grid(row=0, column=1, sticky="w")
    ttk.Entry(execution, textvariable=run_id).grid(
        row=1, column=0, sticky="ew", padx=(0, 20)
    )
    ttk.Spinbox(execution, from_=1, to=256, textvariable=workers, width=7).grid(
        row=1, column=1
    )
    resume = tk.BooleanVar(value=False)
    refresh = tk.BooleanVar(value=False)

    def toggle_resume() -> None:
        if resume.get():
            refresh.set(False)
            refresh_input.state(["disabled"])
        else:
            refresh_input.state(["!disabled"])

    ttk.Checkbutton(
        frame, text="Hervatten", variable=resume, command=toggle_resume
    ).pack(anchor="w", pady=(14, 0))
    ttk.Label(
        frame,
        text="Hervat bestaande runs met dezelfde runnaam.",
        style="Hint.TLabel",
    ).pack(anchor="w", padx=23)
    refresh_input = ttk.Checkbutton(
        frame, text="Bronnen opnieuw ophalen", variable=refresh
    )
    refresh_input.pack(anchor="w", pady=(10, 0))
    ttk.Label(
        frame,
        text="Alleen voor een nieuwe run. Niet samen met hervatten.",
        style="Hint.TLabel",
    ).pack(anchor="w", padx=23)

    def read_plan() -> ScriptPlan:
        if mode.get() == "waterschap":
            arguments = ("--waterbeheercode", AUTHORITIES[authority.get()])
        elif mode.get() == "nederland":
            arguments = ("--area", "nederland")
        elif mode.get() == "polygoon":
            if not polygon_path.get():
                raise ValueError("Kies een polygoonbestand.")
            if not polygon_layer.get():
                raise ValueError("Kies een polygoonlaag.")
            arguments = (
                "--area-file",
                polygon_path.get(),
                "--area-layer",
                polygon_layer.get(),
            )
        else:
            arguments = ("--bounds", *(value.get().strip() for value in bounds))
        try:
            worker_count = int(workers.get())
        except ValueError:
            raise ValueError("Vul voor workers een geheel getal in.") from None
        options = RunSettings(
            tuple(layer for layer in LAYERS if layers[layer].get()),
            arguments,
            run_id.get().strip(),
            worker_count,
            resume.get(),
            refresh.get(),
        )
        return ScriptPlan(options.run_id, tuple(_commands(options)))

    return read_plan


def _window(project: Path) -> None:
    open_window(
        project,
        _build_form,
        title="Waterlagen · Runscript maken",
        description="Kies je gebied en lagen. Sla het script op of start meteen.",
    )


def main() -> int:
    """Open het keuzevenster of start één laag vanuit een opgeslagen script."""
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--start", choices=LAYERS)
    parser.add_argument("--run-id")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--refresh-sources", action="store_true")
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
        _window(project)
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
            ),
            project,
        )
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
