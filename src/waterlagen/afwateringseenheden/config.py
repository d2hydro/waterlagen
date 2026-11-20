"""Configuration types for afwateringseenheden workflows."""

import tomllib
from dataclasses import dataclass
from math import isfinite
from numbers import Real
from pathlib import Path

from ._public_brand_sources import PUBLIC_BRAND_SOURCES

DEFAULT_TILE_SIZE_M = 10000


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
    """One public source or local GeoPackage layer with burn defaults.

    Parameters
    ----------
    path : pathlib.Path, optional
        Local GeoPackage path. Public sources resolve their cache path during
        preparation; callers normally specify only ``bron`` for those sources.
    layer : str, optional
        Local layer name containing lines and/or polygons. Public layer names
        are determined by ``bron``.
    brandwaarde : float, optional
        Signed height change in metres for missing object values.
    prioriteit : int, optional
        Priority for missing object values; higher numbers win.
    bron : str, optional
        Public source name, such as ``bgt_duikers`` or ``bgt_waterdelen``.
        Every configured geometry is burned subject to the overlap priorities;
        culverts require no recognized water-network connections.
    """

    path: Path | None = None
    layer: str | None = None
    brandwaarde: float | None = None
    prioriteit: int | None = None
    bron: str | None = None

    def __post_init__(self) -> None:
        if self.bron is not None:
            if self.bron not in PUBLIC_BRAND_SOURCES:
                raise ValueError(f"Onbekende openbare brandbron: {self.bron}")
            specification = PUBLIC_BRAND_SOURCES[self.bron]
            if self.layer is not None and self.layer != specification.layer:
                raise ValueError("De laagnaam van een openbare bron ligt vast")
            object.__setattr__(self, "layer", specification.layer)
        elif self.path is None:
            raise ValueError("Een lokale brandlaag vereist path en layer")
        if self.path is not None:
            object.__setattr__(self, "path", Path(self.path).resolve())
        if not isinstance(self.layer, str) or not self.layer.strip():
            raise ValueError("Brandlaag.layer must be a non-empty name")
        _validate_defaults(self.brandwaarde, self.prioriteit)
        if self.brandwaarde is not None:
            object.__setattr__(self, "brandwaarde", float(self.brandwaarde))
        if self.prioriteit is not None:
            object.__setattr__(self, "prioriteit", int(self.prioriteit))

    @property
    def openbare_bron(self) -> str | None:
        """Provider selected by the public source name; never a user option."""
        if self.bron is None:
            return None
        return PUBLIC_BRAND_SOURCES[self.bron].provider


@dataclass(frozen=True)
class BrandlagenConfig:
    """Optional burn sources and global fallbacks.

    Parameters
    ----------
    lagen : tuple[Brandlaag, ...]
        Additional sources. The production always prepares HYDAMO connectivity,
        including when no additional sources are configured.
    brandwaarde : float, optional
        Global signed height change in metres, after object and layer values.
    prioriteit : int, optional
        Global priority, after object and layer values. Zero is an explicit value.
    geisoleerde_branddiepte_m : float, optional
        Positive lowering depth for isolated HYDAMO components and tertiary
        waterlines, default 10 metres. Additional sources use their configured
        signed ``brandwaarde`` outside the protected deep HYDAMO network.
    """

    lagen: tuple[Brandlaag, ...] = ()
    brandwaarde: float | None = None
    prioriteit: int | None = None
    geisoleerde_branddiepte_m: float = 10.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "lagen", tuple(self.lagen))
        if not all(isinstance(layer, Brandlaag) for layer in self.lagen):
            raise TypeError("lagen must contain Brandlaag objects")
        _validate_defaults(self.brandwaarde, self.prioriteit)
        if _brand_number(self.geisoleerde_branddiepte_m) < 0:
            raise ValueError("geisoleerde_branddiepte_m must be nonnegative")
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
        and ``[[lagen]]`` entries (public ``bron`` or local ``path``/``layer``,
        and optional defaults
        ``brandwaarde`` and ``prioriteit`` directly on each entry). The root key
        ``geisoleerde_branddiepte_m`` sets the isolated HYDAMO lowering depth.
        Public sources are prepared by the production entry point or an explicit
        call to ``prepare_brand_sources``.

    Returns
    -------
    BrandlagenConfig
        Configuration with absolute local paths and unresolved public sources.
        No source data is read,
        downloaded or prepared by this function.

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
        {"defaults", "lagen", "geisoleerde_branddiepte_m"},
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
        if "rol" in entry or "openbare_bron" in entry:
            raise ValueError("Verouderd brandlagenbestand. Maak een nieuw bestand in de Run Maker.")
        _check_keys(
            entry,
            {
                "path",
                "layer",
                "brandwaarde",
                "prioriteit",
                "bron",
            },
            "laag",
        )
        if "bron" in entry:
            if "path" in entry or "layer" in entry:
                raise ValueError(
                    "Een openbare bron vereist alleen bron; path en layer zijn voor lokale invoer"
                )
            if not isinstance(entry["bron"], str) or not entry["bron"].strip():
                raise ValueError("bron moet een openbare bronnaam zijn")
            layers.append(
                Brandlaag(
                    bron=entry["bron"],
                    brandwaarde=entry.get("brandwaarde"),
                    prioriteit=entry.get("prioriteit"),
                )
            )
            continue
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
            )
        )
    return BrandlagenConfig(
        tuple(layers),
        **defaults,
        geisoleerde_branddiepte_m=values.get("geisoleerde_branddiepte_m", 10.0),
    )
