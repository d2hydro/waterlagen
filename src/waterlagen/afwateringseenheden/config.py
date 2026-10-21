"""Configuration types for afwateringseenheden workflows."""

import tomllib
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from pathlib import Path


def _brand_number(value: object, *, priority: bool = False) -> float | int:
    """Validate explicit values; booleans and numeric text are not numbers here."""
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError("expected a finite number")
    if priority:
        if int(value) != value or not -(2**63) <= value < 2**63:
            raise ValueError("prioriteit must be an int64 integer")
        return int(value)
    return float(value)


@dataclass(frozen=True)
class Brandlaag:
    """One user-supplied GeoPackage layer with optional fallback values.

    Parameters
    ----------
    path : pathlib.Path
        Local GeoPackage path.
    layer : str
        Layer name containing lines and/or polygons.
    brandwaarde : float, optional
        Signed height change in metres for missing object values.
    prioriteit : int, optional
        Priority for missing object values; higher numbers win.
    rol : str, optional
        ``overig`` (ordinary burn), ``water`` or ``duiker`` for water-network processing.
    bron : str, optional
        Culvert source: ``hydamo``, ``bgt`` or ``osm``. Required for culvert layers.
    """

    path: Path
    layer: str
    brandwaarde: float | None = None
    prioriteit: int | None = None
    rol: str = "overig"
    bron: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path).resolve())
        if not isinstance(self.layer, str) or not self.layer.strip():
            raise ValueError("Brandlaag.layer must be a non-empty name")
        _validate_defaults(self.brandwaarde, self.prioriteit)
        if self.rol not in {"overig", "water", "duiker"}:
            raise ValueError("rol must be overig, water or duiker")
        if self.rol == "duiker" and self.bron not in {"hydamo", "bgt", "osm"}:
            raise ValueError("A duiker layer requires bron=hydamo, bgt or osm")
        if self.brandwaarde is not None:
            object.__setattr__(self, "brandwaarde", float(self.brandwaarde))
        if self.prioriteit is not None:
            object.__setattr__(self, "prioriteit", int(self.prioriteit))


@dataclass(frozen=True)
class BrandlagenConfig:
    """Optional burn sources and global fallbacks.

    Parameters
    ----------
    lagen : tuple[Brandlaag, ...]
        Selected sources. No sources preserves the existing burn behaviour.
    brandwaarde : float, optional
        Global signed height change in metres, after object and layer values.
    prioriteit : int, optional
        Global priority, after object and layer values. Zero is an explicit value.
    waternet : bool, optional
        Classify water and culverts jointly on the raster before burning.
    geisoleerde_branddiepte_m : float, optional
        Positive lowering depth for isolated HYDAMO components and tertiary
        waterlines, default 10 metres. Additional sources use their configured
        signed ``brandwaarde`` outside the protected deep HYDAMO network.
    """

    lagen: tuple[Brandlaag, ...] = ()
    brandwaarde: float | None = None
    prioriteit: int | None = None
    waternet: bool = False
    geisoleerde_branddiepte_m: float = 10.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "lagen", tuple(self.lagen))
        if not all(isinstance(layer, Brandlaag) for layer in self.lagen):
            raise TypeError("lagen must contain Brandlaag objects")
        _validate_defaults(self.brandwaarde, self.prioriteit)
        if not isinstance(self.waternet, bool):
            raise TypeError("waternet must be a boolean")
        if _brand_number(self.geisoleerde_branddiepte_m) < 0:
            raise ValueError("geisoleerde_branddiepte_m must be nonnegative")
        if not self.waternet and any(layer.rol != "overig" for layer in self.lagen):
            raise ValueError("water/duiker roles require waternet=true")
        if self.brandwaarde is not None:
            object.__setattr__(self, "brandwaarde", float(self.brandwaarde))
        if self.prioriteit is not None:
            object.__setattr__(self, "prioriteit", int(self.prioriteit))


def _validate_defaults(brandwaarde: float | None, prioriteit: int | None) -> None:
    for name, value in (("brandwaarde", brandwaarde), ("prioriteit", prioriteit)):
        if value is not None:
            try:
                _brand_number(value, priority=name == "prioriteit")
            except ValueError as error:
                raise ValueError(f"Invalid default {name}: {error}") from error


def _check_keys(values: dict, allowed: set[str], description: str) -> None:
    unknown = values.keys() - allowed
    if unknown:
        raise ValueError(f"Unknown {description} keys: {', '.join(sorted(unknown))}")


def read_brandlagen_config(path: Path) -> BrandlagenConfig:
    """Read a TOML burn configuration with paths relative to the TOML file.

    Parameters
    ----------
    path : pathlib.Path
        TOML file with optional ``[defaults]`` (``brandwaarde``, ``prioriteit``)
        and ``[[lagen]]`` entries (``path``, ``layer`` and optional defaults
        ``brandwaarde`` and ``prioriteit`` directly on each entry). Root keys
        ``waternet`` and ``geisoleerde_branddiepte_m`` enable joint connectivity.
        Layer keys ``rol`` and ``bron`` identify water and culvert inputs.

    Returns
    -------
    BrandlagenConfig
        Configuration with absolute source paths. Source data is not read yet.

    Raises
    ------
    ValueError
        Invalid schema, unknown keys or invalid default values.
    TypeError
        Defaults or layer entries have the wrong TOML structure.
    OSError
        The TOML file cannot be read.
    """
    path = Path(path).resolve()
    with path.open("rb") as stream:
        values = tomllib.load(stream)
    _check_keys(
        values,
        {"defaults", "lagen", "waternet", "geisoleerde_branddiepte_m"},
        "configuration",
    )
    defaults = values.get("defaults", {})
    if not isinstance(defaults, dict):
        raise TypeError("defaults must be a TOML table")
    _check_keys(defaults, {"brandwaarde", "prioriteit"}, "defaults")
    entries = values.get("lagen", [])
    if not isinstance(entries, list):
        raise TypeError("lagen must be an array of TOML tables")
    layers = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError("Each lagen entry must be a TOML table")
        _check_keys(
            entry, {"path", "layer", "brandwaarde", "prioriteit", "rol", "bron"}, "laag"
        )
        if not isinstance(entry.get("path"), str) or not entry["path"].strip():
            raise ValueError("Each laag requires a non-empty path")
        if "layer" not in entry:
            raise ValueError("Each laag requires a layer name")
        layers.append(
            Brandlaag(
                path=path.parent / entry["path"],
                layer=entry["layer"],
                brandwaarde=entry.get("brandwaarde"),
                prioriteit=entry.get("prioriteit"),
                rol=entry.get("rol", "overig"),
                bron=entry.get("bron"),
            )
        )
    return BrandlagenConfig(
        tuple(layers),
        **defaults,
        waternet=values.get("waternet", False),
        geisoleerde_branddiepte_m=values.get("geisoleerde_branddiepte_m", 10.0),
    )
