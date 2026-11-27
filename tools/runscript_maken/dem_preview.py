"""Lees de verwachte DEM-invoer zonder bronnen of producties aan te maken."""

import json
from dataclasses import dataclass
from pathlib import Path

from waterlagen._sources import SourcePreparation
from waterlagen.areas import area_from_bounds, area_from_file, resolve_area
from waterlagen.datastore import DataStore
from waterlagen.dem.config import DemConfig
from waterlagen.dem.inputs import find_landuse_input, validate_landuse_run

from .waterlagen import RunSettings, _scope


@dataclass(frozen=True)
class LandusePreview:
    """Korte toelichting met het volledige pad apart voor de interface."""

    state: str
    message: str
    path: str = ""


def preview_landuse(options: RunSettings, run_mode: str) -> LandusePreview:
    """Controleer de huidige keuze; een opgeslagen script kiest pas bij uitvoering.

    Gebiedsgrenzen worden uitsluitend uit de lokale broncache gelezen. De
    bestaande DEM-functies controleren voltooiing, dekking en gebouwcontext.
    Deze controle downloadt niets en maakt geen run of uitvoerbestand aan.
    """
    if "dem" not in options.layers:
        return LandusePreview("hidden", "")
    store = DataStore()
    if options.output_root is not None:
        store = store.model_copy(update={"processed_data_dir": options.output_root})
    scope = _scope(options.area_arguments)
    values = {
        item.flag: item.value for item in options.extra_options if item.layer == "dem"
    }
    explicit = str(values.get("landuse-run", "")).strip()
    context = float(
        values.get("building-max-search-distance-m")
        or DemConfig().building_max_search_distance_m
    )
    metadata_path = (
        store.processed_data_dir / "dem" / scope / options.run_id / "run.json"
    )
    if run_mode in {"resume", "overwrite"} and metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        dependency = metadata.get("landuse_dependency")
        if dependency:
            path = Path(dependency["path"])
            return LandusePreview("recorded", path.name, str(path))
    if not explicit:
        if options.refresh_sources:
            return LandusePreview(
                "create", "Landgebruik wordt eerst berekend (bronnen vernieuwen)."
            )
        if "functioneel_landgebruik" in options.layers:
            return LandusePreview(
                "planned",
                "Landgebruik draait eerst; DEM kiest daarna een geschikte run.",
            )
    flag, *arguments = options.area_arguments
    try:
        if flag == "--bounds":
            area = area_from_bounds(arguments)
        elif flag == "--area-file":
            area = area_from_file(Path(arguments[0]), layer=arguments[2])
        else:
            area = resolve_area(arguments[0], store, SourcePreparation(offline=True))
    except FileNotFoundError:
        return LandusePreview(
            "unknown",
            "Landgebruik wordt bij starten gecontroleerd; gebiedsgrens ontbreekt lokaal.",
        )
    if explicit:
        result = validate_landuse_run(Path(explicit), area, context)
        return LandusePreview(
            "chosen", f"Gekozen landgebruikrun: {result.path.name}", str(result.path)
        )
    result = find_landuse_input(store, area, context)
    if result is not None:
        return LandusePreview(
            "reuse", f"Automatisch: landgebruikrun {result.path.name}", str(result.path)
        )
    return LandusePreview("create", "Landgebruik wordt eerst berekend.")
