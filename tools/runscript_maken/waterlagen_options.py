"""Extra productieopties, hun uitleg en de bijbehorende invoervelden."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from typing import Literal

from waterlagen.dem.config import DemConfig
from waterlagen.rijkswateren.download import RIJKSWATEREN_URL
from waterlagen.settings import settings


@dataclass(frozen=True)
class HelpText:
    """Korte uitleg met een link naar inhoud of productie-instructies."""

    summary: str
    page: str
    section: str = ""
    category: str = "produceren"

    @property
    def url(self) -> str:
        address = f"https://d2hydro.github.io/waterlagen/{self.category}/{self.page}/"
        if self.section:
            address += f"#{self.section}"
        return address


@dataclass(frozen=True)
class ExtraOption:
    """Beschrijving van een formulierveld en het bijbehorende CLI-argument."""

    flag: str
    label: str
    help: HelpText
    kind: Literal[
        "number", "integer", "file", "directory", "toml", "text", "choice", "boolean"
    ]
    default: str | bool = ""
    file_pattern: str = "*"
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    authority_only: bool = False
    hint: str = ""


@dataclass(frozen=True)
class OptionValue:
    """Ingevulde waarde voor één optie van één kaartlaag."""

    layer: str
    flag: str
    value: str | bool


DEM = DemConfig()
EXTRA_OPTIONS = {
    "functioneel_landgebruik": (
        ExtraOption(
            "mapping-csv",
            "Eigen landgebruikscodetabel (.csv)",
            HelpText(
                "Gebruik een eigen tabel voor de indeling en kleuren van landgebruik.",
                "landgebruik-codetabel",
            ),
            "file",
            file_pattern="*.csv",
        ),
        ExtraOption(
            "bgt-path",
            "Voorbereid BGT-bestand (.gpkg)",
            HelpText(
                "Gebruik een lokaal, voorbereid BGT-GeoPackage.",
                "landgebruik",
                "vooraf",
            ),
            "file",
            file_pattern="*.gpkg",
        ),
        ExtraOption(
            "building-context-m",
            "Marge voor buurpanden (m)",
            HelpText(
                "Neemt ook buurpanden buiten de tegel mee, zodat DEM daar geen maaiveldhoogtes meet. Kies minstens de maximale zoekafstand rond een pand.",
                "landgebruik",
                "starten",
            ),
            "number",
            "5",
            minimum=0,
        ),
    ),
    "dem": (
        ExtraOption(
            "landuse-run",
            "Landgebruikrun (optioneel)",
            HelpText(
                "Kies de map van een afgeronde landgebruikrun. Leeg laten voor automatische keuze.",
                "dem",
                "landgebruik-vinden-of-produceren",
            ),
            "directory",
        ),
        ExtraOption(
            "ahn-vrt",
            "Eigen DTM-VRT (.vrt)",
            HelpText(
                "Kies uw eigen maaiveldmodel. Laat dit veld leeg voor AHN.",
                "dem",
                "hoogtebron",
            ),
            "file",
            file_pattern="*.vrt",
        ),
        ExtraOption(
            "building-initial-buffer-m",
            "Startafstand rond pand (m)",
            HelpText(
                "Eerste afstand rond een gebouw om bruikbare terreinhoogtes te zoeken.",
                "dem",
                "instellingen-en-workers",
            ),
            "number",
            str(DEM.building_initial_buffer_m),
            minimum=0,
        ),
        ExtraOption(
            "building-buffer-step-m",
            "Afstand per extra stap (m)",
            HelpText(
                "Als er rond het pand geen bruikbare terreinhoogte is gevonden, wordt de zoekafstand met deze stap vergroot.",
                "dem",
                "instellingen-en-workers",
            ),
            "number",
            str(DEM.building_buffer_step_m),
            minimum=0,
        ),
        ExtraOption(
            "building-max-search-distance-m",
            "Maximale afstand rond pand (m)",
            HelpText(
                "Tot deze afstand vanaf de buitenrand van het pand worden terreinhoogtes gezocht om het vloerpeil te schatten.",
                "dem",
                "instellingen-en-workers",
            ),
            "number",
            str(DEM.building_max_search_distance_m),
            minimum=0,
        ),
        ExtraOption(
            "building-percentile",
            "Hoogtepercentiel (%)",
            HelpText(
                "Kiest het hoogtepercentiel uit de gevonden terreinhoogtes; standaard 75.",
                "dem",
                "instellingen-en-workers",
            ),
            "number",
            str(DEM.building_percentile),
            minimum=0,
            maximum=100,
        ),
        ExtraOption(
            "building-offset-m",
            "Toeslag gebouwhoogte (m)",
            HelpText(
                "Tel deze hoogte bij het geschatte vloerpeil op; 0 schakelt de toeslag uit.",
                "dem",
                "instellingen-en-workers",
            ),
            "number",
            str(DEM.building_offset_m),
        ),
        ExtraOption(
            "building-workers",
            "Workers voor gebouwhoogten",
            HelpText(
                "Hoeveel groepen gebouwen tegelijk worden verwerkt, vóór de berekening van DEM-tegels.",
                "dem",
                "instellingen-en-workers",
            ),
            "integer",
            str(settings.dem_building_workers),
            minimum=1,
        ),
        ExtraOption(
            "interpolation-max-distance-m",
            "Zoekafstand bij ontbrekende hoogte (m)",
            HelpText(
                "Schat ontbrekende terreinhoogtes met metingen binnen deze afstand; 0 schakelt dit uit.",
                "dem",
                "instellingen-en-workers",
            ),
            "number",
            str(DEM.interpolation_max_distance_m),
            minimum=0,
        ),
    ),
    "inwoners": (
        ExtraOption(
            "no-geoparquet",
            "Alleen GeoPackage schrijven",
            HelpText(
                "Schrijf alleen een GeoPackage, zonder een extra GeoParquet-bestand.",
                "inwoners-personenautos",
                "uitvoer",
            ),
            "boolean",
            False,
        ),
    ),
    "autos": (
        ExtraOption(
            "no-geoparquet",
            "Alleen GeoPackage schrijven",
            HelpText(
                "Schrijf alleen een GeoPackage, zonder een extra GeoParquet-bestand.",
                "inwoners-personenautos",
                "uitvoer",
            ),
            "boolean",
            False,
        ),
    ),
    "afwateringseenheden": (
        ExtraOption(
            "brandlagen-config",
            "Extra brandlagen (.toml)",
            HelpText(
                "Open, maak of bewerk de instellingen voor extra brandlagen.",
                "afwateringseenheden",
                "extra-brandlagen-kiezen",
            ),
            "toml",
            file_pattern="*.toml",
        ),
        ExtraOption(
            "eigen-hydamo",
            "Eigen HyDAMO (.gpkg)",
            HelpText(
                "Vervang de GKW-gegevens van alle gekozen waterschappen door één eigen HyDAMO-GeoPackage.",
                "afwateringseenheden",
                "aanvullende-instellingen",
            ),
            "file",
            file_pattern="*.gpkg",
            authority_only=True,
        ),
        ExtraOption(
            "dem-resampling",
            "Hoogte kiezen per rekencel",
            HelpText(
                "Kies hoe het hoogteraster naar de rekencellen wordt omgerekend.",
                "afwateringseenheden",
                "dem-resampling-kiezen",
            ),
            "choice",
            "min",
            choices=(
                "min",
                "average",
                "nearest",
                "bilinear",
                "cubic",
                "cubic_spline",
                "lanczos",
                "max",
                "med",
                "q1",
                "q3",
            ),
        ),
        ExtraOption(
            "duiker-tolerance",
            "Koppelafstand duikers (m)",
            HelpText(
                "Maximale afstand tussen een duikeruiteinde en een primaire waterloop.",
                "afwateringseenheden",
                "aanvullende-instellingen",
            ),
            "number",
            "0.5",
            minimum=0,
        ),
        ExtraOption(
            "max-aansluitlengte",
            "Maximale aansluitlengte (m)",
            HelpText(
                "Sluit korte directe aansluitstukken uit als afwateringsdoel. Leeg laat deze grens uit.",
                "afwateringseenheden",
                "aanvullende-instellingen",
            ),
            "number",
            minimum=0,
            hint="Leeg: geen extra uitsluiting.",
        ),
        ExtraOption(
            "max-complex-routelengte",
            "Maximale complexroute (m)",
            HelpText(
                "Maximale parallelle route met een eigen kunstwerk; 0 schakelt deze controle uit.",
                "afwateringseenheden",
                "aanvullende-instellingen",
            ),
            "number",
            "100",
            minimum=0,
        ),
        ExtraOption(
            "rijkswateren-url",
            "Rijkswateren-URL",
            HelpText(
                "Gebruik een ander downloadadres voor de Rijkswaterenbron.",
                "afwateringseenheden",
                "aanvullende-instellingen",
            ),
            "text",
            RIJKSWATEREN_URL,
        ),
        ExtraOption(
            "overige-waterschappen",
            "Ook afwateren naar waterlopen van andere waterschappen",
            HelpText(
                "Sta waterlopen van andere waterschappen toe als afwateringsdoel binnen het gekozen gebied.",
                "afwateringseenheden",
                "aanvullende-instellingen",
            ),
            "boolean",
            False,
            authority_only=True,
        ),
    ),
}


def _number(option: ExtraOption, value: str) -> float | int:
    try:
        number = int(value) if option.kind == "integer" else float(value)
    except ValueError:
        raise ValueError(f"{option.label}: vul een geldig getal in.") from None
    if not isfinite(number):
        raise ValueError(f"{option.label}: vul een eindig getal in.")
    if option.minimum is not None and number < option.minimum:
        raise ValueError(f"{option.label}: vul minstens {option.minimum:g} in.")
    if option.maximum is not None and number > option.maximum:
        raise ValueError(f"{option.label}: vul hoogstens {option.maximum:g} in.")
    return number


def _validate_geopackage(path: Path, flag: str) -> None:
    import pyogrio

    try:
        layers = pyogrio.list_layers(path)
        if not len(layers) or pyogrio.read_info(path, layer=0)["driver"] != "GPKG":
            raise ValueError("Kies een geldig GeoPackage (.gpkg).")
    except (OSError, RuntimeError) as error:
        raise ValueError("Kan het GeoPackage niet openen.") from error
    if flag == "eigen-hydamo":
        required = {"hydroobject", "gemaal", "stuw", "duikersifonhevel"}
    else:
        from waterlagen.functioneel_landgebruik.landgebruik_berekenen import (
            FunctioneelLandgebruikLayers,
        )

        required = {
            name
            for key, name in asdict(FunctioneelLandgebruikLayers()).items()
            if key.startswith("bgt_")
        }
    missing = required.difference(layers[:, 0])
    if missing:
        raise ValueError("Ontbrekende lagen: " + ", ".join(sorted(missing)) + ".")


def _validate_landuse_folder(path: Path) -> None:
    try:
        metadata = json.loads((path / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("Kies een runmap met een leesbaar run.json.") from error
    if (
        not isinstance(metadata, dict)
        or metadata.get("dataset") != "functioneel_landgebruik"
        or metadata.get("status") != "complete"
    ):
        raise ValueError("Kies een afgeronde landgebruikrun.")
    for name in ("tiles.gpkg", "landgebruik_met_code.csv"):
        if not (path / name).is_file():
            raise ValueError(f"{name} ontbreekt in de runmap.")
    tiles = path / "tiles"
    legacy_tiles = tiles.glob("functioneel_landgebruik*.tif")
    nested_tiles = tiles.glob("*/functioneel_landgebruik.tif")
    if not any(tile.is_file() for tile in legacy_tiles) and not any(
        tile.is_file() for tile in nested_tiles
    ):
        raise ValueError("Geen landgebruikrasters gevonden in de runmap.")


def validate_option_path(option: ExtraOption, value: str | Path) -> Path:
    """Check whether a chosen path can serve as input without loading spatial data."""
    path = Path(value).resolve()
    if option.kind == "directory":
        if not path.is_dir():
            raise ValueError("Map niet gevonden.")
        _validate_landuse_folder(path)
        return path
    if not path.is_file():
        raise ValueError("Bestand niet gevonden.")
    suffix = option.file_pattern.removeprefix("*")
    if path.suffix.lower() != suffix:
        raise ValueError(f"Kies een bestand van het type {suffix}.")
    if suffix == ".gpkg":
        _validate_geopackage(path, option.flag)
    elif suffix == ".vrt":
        import rasterio

        try:
            with rasterio.open(path) as raster:
                if raster.driver != "VRT" or not raster.count or raster.crs is None:
                    raise ValueError("Kies een DTM-VRT met een coördinatenstelsel.")
        except rasterio.errors.RasterioIOError as error:
            raise ValueError("Kan de DTM-VRT niet openen.") from error
    elif suffix == ".csv":
        from waterlagen.functioneel_landgebruik.landgebruikstabel import (
            load_landuse_table,
        )

        try:
            load_landuse_table(path)
        except (OSError, ValueError) as error:
            raise ValueError(
                "Ongeldige codetabel. Gebruik UTF-8 en puntkomma’s."
            ) from error
    elif suffix == ".toml":
        from waterlagen.afwateringseenheden.config import read_brandlagen_config

        try:
            read_brandlagen_config(path)
        except (OSError, TypeError, ValueError) as error:
            raise ValueError(f"Ongeldige brandlagen-TOML: {error}") from error
    return path


def extra_arguments(
    layer: str, values: tuple[OptionValue, ...], *, authority: bool
) -> list[str | Path]:
    """Controleer gekozen opties en maak alleen de bijbehorende CLI-argumenten."""
    options = {option.flag: option for option in EXTRA_OPTIONS[layer]}
    selected = [value for value in values if value.layer == layer]
    seen = set()
    arguments: list[str | Path] = []
    dem_numbers = {}
    for choice in selected:
        if choice.flag not in options or choice.flag in seen:
            raise ValueError(f"Onbekende of dubbele optie voor {layer}: {choice.flag}")
        seen.add(choice.flag)
        option = options[choice.flag]
        if option.authority_only and not authority and choice.value not in ("", False):
            raise ValueError(f"{option.label} vereist een gekozen waterschap.")
        if option.kind == "boolean":
            if not isinstance(choice.value, bool):
                raise ValueError(f"{option.label}: kies aan of uit.")
            if choice.value:
                arguments.append("--" + option.flag)
            continue
        if not isinstance(choice.value, str):
            raise ValueError(f"{option.label}: ongeldige waarde.")
        value = choice.value.strip()
        if not value:
            if option.default != "":
                raise ValueError(f"Vul {option.label.lower()} in.")
            continue
        argument: str | Path = value
        is_default = value == option.default
        if option.kind in {"number", "integer"}:
            number = _number(option, value)
            if option.default != "":
                is_default = number == float(str(option.default))
            if layer == "dem" and option.flag != "building-workers":
                dem_numbers[option.flag.replace("-", "_")] = number
        elif option.kind in {"file", "directory", "toml"}:
            try:
                argument = validate_option_path(option, value)
            except ValueError as error:
                raise ValueError(f"{option.label}: {error}") from error
        elif option.kind == "choice" and value not in option.choices:
            raise ValueError(f"Kies een geldige waarde voor {option.label.lower()}.")
        if not is_default or option.flag == "building-workers":
            arguments.extend(["--" + option.flag, argument])
    if layer == "dem":
        if dem_numbers.get(
            "building_initial_buffer_m", DEM.building_initial_buffer_m
        ) > dem_numbers.get(
            "building_max_search_distance_m", DEM.building_max_search_distance_m
        ):
            raise ValueError(
                "De eerste zoekafstand mag niet groter zijn dan de maximale zoekafstand."
            )
        for name in (
            "building_initial_buffer_m",
            "building_buffer_step_m",
            "building_max_search_distance_m",
        ):
            if dem_numbers.get(name, getattr(DEM, name)) <= 0:
                raise ValueError(
                    "De zoekafstanden en zoekstap voor gebouwen moeten groter zijn dan 0."
                )
        DemConfig(**dem_numbers)
    return arguments
