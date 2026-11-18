"""Verbind het kaartvenster met de bestaande Pixi-opdrachten."""

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
from waterlagen.settings import settings

from .map_data import map_boundaries, map_feature, save_polygon
from .script import build_batch_script, save_script
from .waterlagen import (
    AUTHORITIES,
    LAYER_HELP,
    LAYERS,
    RunSettings,
    _existing_layers,
    _start_code_update,
    _validate,
    _window_commands,
)
from .waterlagen_options import EXTRA_OPTIONS, OptionValue, validate_option_path
from .waterlagen_runfile import read_runfile

if TYPE_CHECKING:
    from .native_dialogs import NativeDialogs


def run_settings(values: dict) -> RunSettings:
    """Controleer formulierkeuzes vóór het maken van een commando."""
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
        area_from_file(path, layer=layer)
        area = ("--area-file", str(path), "--area-layer", layer)
    else:
        raise ValueError("Kies een gebied.")
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
    if (
        "dem" in layers
        and values.get("dem_landuse_mode") == "manual"
        and not any(
            item.layer == "dem"
            and item.flag == "landuse-run"
            and str(item.value).strip()
            for item in choices
        )
    ):
        raise ValueError("Kies een landgebruikrun of schakel terug naar Automatisch.")
    options = RunSettings(
        layers,
        area,
        str(values.get("run_id", "")).strip(),
        workers,
        refresh_sources=bool(values.get("refresh_sources")),
        debug=bool(values.get("debug")),
        extra_options=choices,
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

    def bootstrap(self) -> dict:
        if self.boundaries is None:
            self.boundaries = map_boundaries(
                {code: name for name, code in AUTHORITIES.items()}
            )
        return {
            **self.boundaries,
            "layers": list(LAYERS.items()),
            "project": str(self.project),
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

    def commands(self, values: dict) -> list[str]:
        from dataclasses import replace

        options = run_settings(values)
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
        if action == "bootstrap":
            return self.bootstrap()
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
            result = form_values(read_runfile(path, self.project))
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
