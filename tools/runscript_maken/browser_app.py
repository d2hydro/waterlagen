"""Verbind het kaartvenster met de bestaande Pixi-opdrachten."""

import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from waterlagen.areas import (
    area_file_layers,
    area_from_bounds,
    area_from_file,
    parse_authority_codes,
)
from waterlagen.datastore import DataStore
from waterlagen.settings import settings

from .ahn_preview import CoveragePreview
from .map_data import map_boundaries, map_feature, save_polygon
from .script import build_batch_script, save_script
from .waterlagen import (
    AUTHORITIES,
    LAYER_HELP,
    LAYERS,
    RunSettings,
    _existing_layers,
    _scope,
    _start_code_update,
    _validate,
    _window_commands,
)
from .waterlagen_options import EXTRA_OPTIONS, OptionValue, validate_option_path
from .waterlagen_runfile import read_runfile

if TYPE_CHECKING:
    from .native_dialogs import NativeDialogs


def area_arguments(values: dict, *, validate_file: bool = True) -> tuple[str, ...]:
    """Lees uitsluitend de gebiedskeuze, onafhankelijk van overige formuliervelden."""
    mode = values.get("mode")
    if mode == "authorities":
        codes = parse_authority_codes(",".join(values.get("authorities", [])))
        if not set(codes).issubset(AUTHORITIES.values()):
            raise ValueError("Kies een geldig waterschap.")
        area = ("--waterbeheercode", ",".join(codes))
    elif mode == "country":
        area = ("--area", "nederland")
    elif mode == "bounds":
        bounds = values.get("bounds", [])
        area_from_bounds(bounds)
        area = ("--bounds", *(str(value) for value in bounds))
    elif mode in {"file", "draw"}:
        if mode == "draw" and not values.get("drawing_saved"):
            raise ValueError("Sla de getekende polygoon eerst op als GeoPackage.")
        path = Path(values.get("area_file", "")).resolve()
        layer = values.get("area_layer", "")
        if validate_file:
            area_from_file(path, layer=layer)
        area = ("--area-file", str(path), "--area-layer", layer)
    else:
        raise ValueError("Kies een gebied.")
    return area


def run_settings(values: dict) -> RunSettings:
    """Controleer formulierkeuzes vóór het maken van een commando."""
    area = area_arguments(values)
    requested = values.get("layers", [])
    if any(layer not in LAYERS for layer in requested):
        raise ValueError("Onbekende basislaag.")
    layers = tuple(layer for layer in LAYERS if layer in requested)
    try:
        workers = int(str(values.get("workers", 8)))
    except ValueError:
        raise ValueError("Vul voor workers een geheel getal in.") from None
    choices = tuple(
        OptionValue(**item)
        for item in values.get("extra_options", [])
        if item.get("layer") in layers
    )
    options = RunSettings(
        layers,
        area,
        str(values.get("run_id", "")).strip(),
        workers,
        refresh_sources=bool(values.get("refresh_sources")),
        debug=bool(values.get("debug")),
        extra_options=choices,
        download_root=Path(values["download_root"]).resolve()
        if values.get("download_root")
        else None,
        datastore_file=Path(os.environ["WATERLAGEN_DATASTORE"])
        if os.getenv("WATERLAGEN_DATASTORE")
        else None,
        output_root=Path(values["output_root"]).resolve()
        if values.get("output_root")
        else None,
    )
    _validate(options)
    return options


def form_values(run: RunSettings) -> dict:
    """Zet een bestaande run terug in de zichtbare formuliervelden."""
    flag, *arguments = run.area_arguments
    mode = {
        "--waterbeheercode": "authorities",
        "--area": "country",
        "--bounds": "bounds",
        "--area-file": "file",
    }[flag]
    return {
        "mode": mode,
        "authorities": arguments[0].split(",") if mode == "authorities" else [],
        "bounds": arguments if mode == "bounds" else [],
        "area_file": arguments[0] if mode == "file" else "",
        "area_layer": arguments[2] if mode == "file" else "",
        "layers": run.layers,
        "run_id": run.run_id,
        "download_root": str(run.download_root) if run.download_root else "",
        "output_root": str(run.output_root) if run.output_root else "",
        "workers": run.workers,
        "refresh_sources": run.refresh_sources,
        "debug": run.debug,
        "run_mode": "overwrite" if run.overwrite else "resume",
        "extra_options": [asdict(item) for item in run.extra_options],
    }


class RunApplication:
    """Domeinfuncties voor het lokale kaartvenster, zonder eigen productielogica."""

    def __init__(self, project: Path, dialogs: "NativeDialogs") -> None:
        self.project = project
        self.dialogs = dialogs
        self.boundaries = None
        self.startup_message = "Gebiedsgrenzen opzoeken in de datastore…"
        self.coverage = CoveragePreview()

    def bootstrap(self) -> dict:
        if self.boundaries is None:
            self.boundaries = map_boundaries(
                {code: name for name, code in AUTHORITIES.items()},
                self._startup_progress,
            )
        return {
            **self.boundaries,
            "layers": list(LAYERS.items()),
            "project": str(self.project),
            "default_output_root": str(DataStore().processed_data_dir.resolve()),
            "crs": str(settings.crs),
            "run_id": datetime.now().strftime("proef-%Y%m%d-%H%M%S"),
            "options": {
                layer: [{**asdict(option), "url": option.help.url} for option in items]
                for layer, items in EXTRA_OPTIONS.items()
            },
            "layer_help": {
                layer: {"summary": help.summary, "url": help.url}
                for layer, help in LAYER_HELP.items()
            },
        }

    def _startup_progress(self, message: str) -> None:
        self.startup_message = message

    def commands(self, values: dict) -> list[str]:
        from dataclasses import replace

        options = run_settings(values)
        fixed = next(
            (
                item.value
                for item in options.extra_options
                if item.layer == "dem" and item.flag == "ahn-version" and item.value
            ),
            None,
        )
        if fixed:
            result = self.coverage.status(options.area_arguments)
            available, total = result["counts"][fixed]
            if (
                (fixed == "6" and result["phase"] != "ready")
                or not total
                or available != total
            ):
                raise ValueError(
                    f"AHN{fixed} heeft geen bevestigde volledige dekking voor dit gebied."
                )
        existing = _existing_layers(options)
        if existing and values.get("run_mode") not in {"resume", "overwrite"}:
            raise ValueError("Deze run bestaat al. Kies hervatten of overschrijven.")
        options = replace(
            options,
            resume=bool(existing) and values.get("run_mode") == "resume",
            overwrite=bool(existing) and values.get("run_mode") == "overwrite",
        )
        _validate(options)
        return _window_commands(options)

    def dispatch(self, action: str, values: dict) -> dict:
        if action == "startup_status":
            return {"message": self.startup_message}
        if action == "bootstrap":
            return self.bootstrap()
        if action == "ahn_result":
            import webbrowser

            run = run_settings(values)
            report = (
                run.results_directory
                / "dem"
                / _scope(run.area_arguments)
                / run.run_id
                / "ahn_overzicht.html"
            )
            if not report.is_file():
                raise ValueError("Er is nog geen AHN-overzicht voor deze run.")
            webbrowser.open(report.resolve().as_uri())
            return {}
        if action == "choose_download_root":
            path = self.dialogs.directory(
                "Sta ontbrekende AHN-tegels toe in deze map",
                initialdir=DataStore().source_data_dir,
            )
            return {"path": str(path)} if path else {"cancelled": True}
        if action == "choose_output_root":
            initial = (
                Path(values["current"])
                if values.get("current")
                else DataStore().processed_data_dir
            )
            path = self.dialogs.directory("Kies de resultatenmap", initialdir=initial)
            return {"path": str(path)} if path else {"cancelled": True}
        if action == "ahn_coverage":
            return self.coverage.status(
                area_arguments(values, validate_file=False),
                force=values.get("force") is True,
            )
        if action == "preview":
            return {"commands": self.commands(values)}
        if action == "dem_landuse":
            from .dem_preview import preview_landuse

            try:
                result = preview_landuse(
                    run_settings(values), values.get("run_mode", "")
                )
            except (ValueError, KeyError, OSError, RuntimeError) as error:
                return {"state": "error", "message": str(error), "path": ""}
            return asdict(result)
        if action == "save":
            store = DataStore()
            layers = set(values.get("layers", []))
            sources = {"bag"} if layers.intersection({"inwoners", "autos"}) else set()
            if "functioneel_landgebruik" in layers:
                sources.update({"bag", "brp", "bgt", "top10nl"})
            for key in sorted(sources):
                explicit = getattr(store, key + "_file")
                if explicit and not explicit.is_file():
                    raise ValueError(f"{key.upper()}-bestand ontbreekt: {explicit}. Kies een ander bestand in de datastore.")
            commands = self.commands(values)
            path = self.dialogs.save("Run opslaan", ".bat", values["run_id"] + ".bat")
            if path is None:
                return {"cancelled": True}
            if path.suffix.lower() != ".bat":
                raise ValueError("Bewaar de run als .bat.")
            script = build_batch_script(commands, self.project, path)
            process = save_script(
                script, path, self.project, start=bool(values.get("start"))
            )
            return {"path": str(path), "started": process is not None}
        if action == "run_load":
            path = self.dialogs.open("Run laden", "*.bat *.ps1")
            if path is None:
                return {"cancelled": True}
            run = read_runfile(path, self.project)
            if run.datastore_file and str(run.datastore_file) != os.getenv(
                "WATERLAGEN_DATASTORE"
            ):
                raise ValueError(
                    f"Open de Runmaker met de datastore van dit script: {run.datastore_file}"
                )
            result = form_values(run)
            result["path"] = str(path)
            return result
        if action == "polygon_file":
            path = self.dialogs.open(
                "Polygoonbestand kiezen", "*.gpkg *.geojson *.json"
            )
            if path is None:
                return {"cancelled": True}
            return {"path": str(path), "layers": area_file_layers(path)}
        if action == "polygon_layer":
            path = Path(values["path"])
            layer = values["layer"]
            return {
                "feature": map_feature(area_from_file(path, layer=layer)),
                "layers": area_file_layers(path),
            }
        if action == "bounds":
            return {"feature": map_feature(area_from_bounds(values["bounds"]))}
        if action == "draw_save":
            # Eerst valideren, daarna laat het opslagvenster de bestemming kiezen.
            coordinates = values["coordinates"]
            from shapely.geometry import Polygon

            polygon = Polygon(coordinates)
            if len(coordinates) < 3 or not polygon.is_valid or polygon.area == 0:
                raise ValueError("Teken een gesloten polygoon zonder kruisende lijnen.")
            path = self.dialogs.save("Gebied opslaan", ".gpkg", "eigen-gebied.gpkg")
            if path is None:
                return {"cancelled": True}
            return {
                "path": str(path),
                "layer": "gebied",
                "feature": save_polygon(coordinates, path),
            }
        if action in {"browse", "validate_path"}:
            option = next(
                (
                    option
                    for option in EXTRA_OPTIONS.get(values.get("layer"), [])
                    if option.flag == values.get("flag")
                ),
                None,
            )
            if option is None or option.kind not in {"file", "directory", "toml"}:
                raise ValueError("Deze optie heeft geen bestandskeuze.")
            if action == "browse":
                path = (
                    self.dialogs.directory(option.label)
                    if option.kind == "directory"
                    else self.dialogs.open(option.label, option.file_pattern)
                )
                if path is None:
                    return {"cancelled": True}
            else:
                path = Path(values["path"])
            try:
                checked = validate_option_path(option, path)
            except ValueError as error:
                return {"path": str(path), "error": str(error)}
            return {"path": str(checked)}
        if action == "brand_edit":
            return {"path": self.dialogs.brandlagen(values.get("path", ""))}
        if action == "update":
            _start_code_update(self.project)
            return {"closing": True}
        raise ValueError("Onbekende opdracht.")
