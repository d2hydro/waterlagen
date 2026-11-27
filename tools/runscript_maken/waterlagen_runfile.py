"""Lees de productie-instellingen uit een opgeslagen Pixi-runfile."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .script import read_batch_commands, read_commands
from .waterlagen import AUTHORITIES, LAYERS, WORKER_LAYERS, RunSettings, _validate
from .waterlagen_options import EXTRA_OPTIONS, OptionValue


def read_runfile(path: Path, project: Path) -> RunSettings:
    """Lees een BAT- of PowerShell-runfile en controleer de productieopties."""
    if path.suffix.lower() not in {".bat", ".ps1"} or path.stat().st_size > 2_000_000:
        raise ValueError("Kies een runfile (.bat of .ps1) kleiner dan 2 MB.")
    try:
        text = path.read_text(encoding="utf-8-sig")
        commands = (
            read_batch_commands(text)
            if path.suffix.lower() == ".bat"
            else read_commands(text)
        )
    except UnicodeError:
        raise ValueError("Bewaar de runfile als UTF-8 en probeer opnieuw.") from None
    runs = []
    worker_counts = set()
    for words in commands:
        if words[:2] != ["pixi", "run"]:
            raise ValueError("De runfile mag alleen pixi run-commando's bevatten.")
        words = words[2:]
        if words and words[0] == "--locked":
            words = words[1:]
        if not words or words[0] not in LAYERS:
            raise ValueError("Onbekende basislaag in de runfile.")
        layer, *arguments = words
        extra = {option.flag: option for option in EXTRA_OPTIONS[layer]}
        lengths = {
            "run-id": 1,
            "output-root": 1,
            "datastore": 1,
            "ahn-download-dir": 1,
            "workers": 1,
            "resume": 0,
            "overwrite": 0,
            "refresh-sources": 0,
            "debug": 0,
            "waterbeheercode": 1,
            "area": 1,
            "bounds": 4,
            "area-file": 1,
            "area-layer": 1,
            **{
                flag: 0 if option.kind == "boolean" else 1
                for flag, option in extra.items()
            },
        }
        values = {}
        position = 0
        while position < len(arguments):
            flag = arguments[position].removeprefix("--")
            if not arguments[position].startswith("--") or flag not in lengths:
                raise ValueError(
                    f"Optie niet ondersteund in Run maken: {arguments[position]}"
                )
            if flag in values:
                raise ValueError(f"Optie staat dubbel in de runfile: --{flag}")
            count = lengths[flag]
            items = arguments[position + 1 : position + 1 + count]
            if len(items) != count or any(item.startswith("--") for item in items):
                raise ValueError(f"Vul een waarde in voor --{flag}.")
            values[flag] = items
            position += 1 + count
        if "run-id" not in values:
            raise ValueError("De runfile heeft geen --run-id.")
        area_flags = [
            flag
            for flag in ("waterbeheercode", "area", "bounds", "area-file")
            if flag in values
        ]
        if len(area_flags) > 1:
            raise ValueError("Gebruik één gebied per commando.")
        area_flag = area_flags[0] if area_flags else "area"
        area_values = values.get(area_flag, ["nederland"])
        if area_flag == "waterbeheercode":
            from waterlagen.areas import parse_authority_codes

            codes = parse_authority_codes(area_values[0])
            if not set(codes).issubset(AUTHORITIES.values()):
                raise ValueError(
                    "Een waterbeheercode staat niet in de waterschapskeuze."
                )
            area_values = [",".join(codes)]
        if area_flag == "area" and area_values != ["nederland"]:
            raise ValueError(
                "Gebruik een waterschap, Nederland, rechthoek of polygoonbestand."
            )
        if "area-layer" in values and area_flag != "area-file":
            raise ValueError("--area-layer vereist een polygoonbestand.")
        if area_flag == "area-file":
            from waterlagen import areas

            if not hasattr(areas, "area_file_layers"):
                raise ValueError("Deze versie ondersteunt polygoonbestanden nog niet.")
            polygon = (project / area_values[0]).resolve()
            names = areas.area_file_layers(polygon)
            selected = values.get("area-layer", names if len(names) == 1 else [])
            if len(selected) != 1 or selected[0] not in names:
                raise ValueError("Geef de polygoonlaag op met --area-layer.")
            area_values = [str(polygon), "--area-layer", selected[0]]
        area_arguments = ("--" + area_flag, *area_values)
        try:
            workers = int(values.get("workers", ["8"])[0])
        except ValueError:
            raise ValueError("Vul voor workers een geheel getal in.") from None
        if layer in WORKER_LAYERS:
            worker_counts.add(workers)
        elif "workers" in values:
            raise ValueError(f"{LAYERS[layer]} gebruikt geen --workers.")
        choices = []
        for flag, option in extra.items():
            if flag not in values:
                continue
            value = True if option.kind == "boolean" else values[flag][0]
            if flag == "ahn-version" and value == "latest":
                continue
            if option.kind in {"file", "directory", "toml"}:
                value = str((project / value).resolve())
            choices.append(OptionValue(layer, flag, value))
        profile = None
        if "datastore" in values:
            value = values["datastore"][0]
            profile = (
                path.parent / value[5:]
                if value.startswith("%~dp0")
                else project / value
            ).resolve()
        run = RunSettings(
            (layer,),
            area_arguments,
            values["run-id"][0],
            workers,
            resume="resume" in values,
            overwrite="overwrite" in values,
            refresh_sources="refresh-sources" in values,
            debug="debug" in values,
            extra_options=tuple(choices),
            datastore_file=profile,
            download_root=(project / values["ahn-download-dir"][0]).resolve()
            if "ahn-download-dir" in values
            else None,
            output_root=(project / values["output-root"][0]).resolve()
            if "output-root" in values
            else None,
        )
        _validate(run)
        runs.append(run)
    first = runs[0]
    if any(
        (
            run.area_arguments,
            run.run_id,
            run.debug,
            run.refresh_sources,
            run.output_root,
            run.datastore_file,
            run.download_root,
        )
        != (
            first.area_arguments,
            first.run_id,
            first.debug,
            first.refresh_sources,
            first.output_root,
            first.datastore_file,
            first.download_root,
        )
        for run in runs
    ):
        raise ValueError(
            "Gebruik hetzelfde gebied, dezelfde runnaam en uitvoeropties voor alle lagen."
        )
    if len(worker_counts) > 1:
        raise ValueError("Gebruik hetzelfde aantal workers voor tegels bij alle lagen.")
    layers = tuple(run.layers[0] for run in runs)
    if len(set(layers)) != len(layers):
        raise ValueError("Een basislaag staat dubbel in deze runfile.")
    if layers != tuple(layer for layer in LAYERS if layer in layers):
        raise ValueError(
            "Zet de lagen in productievolgorde: landgebruik, DEM, inwoners, auto's, afwateringseenheden."
        )
    combined = replace(
        first,
        layers=layers,
        workers=next(iter(worker_counts), 8),
        resume=any(run.resume for run in runs),
        overwrite=any(run.overwrite for run in runs),
        extra_options=tuple(choice for run in runs for choice in run.extra_options),
    )
    _validate(combined)
    return combined
