import re
from collections.abc import Iterable
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

from waterlagen import _geopandas as wgpd
from waterlagen import datastore
from waterlagen._downloads import validate_geopackage
from waterlagen.logger import get_logger

from .download import (
    DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
    WATERSCHAPSGRENZEN_FILENAME,
    bestuurlijke_gebieden_path,
)

logger = get_logger(name=__name__)

LANDSGRENS_LAYER = "landgebied"
WATERSCHAPSGRENZEN_LAYER = "waterschap"
UNIFORM_AREA_COLUMNS = (
    "naam",
    "bgt_code",
    "waterbeheercode",
    "bron",
    "versie",
    "geometry",
)
NEN3610_WATERBEHEERCODE_PATTERN = re.compile(r"^NL\.WBHCODE\.(\d+)\.")


def _default_waterschapsgrenzen_path() -> Path:
    """Return the default datastore path for waterschapsgrenzen."""
    return datastore.administratieve_gebieden_dir / WATERSCHAPSGRENZEN_FILENAME


def _read_source_layer(path: Path, *, layer: str, source_name: str) -> gpd.GeoDataFrame:
    """Read a required layer from a validated administrative GeoPackage."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{source_name} source GeoPackage is missing: {path}. "
            "Download it before reading this layer."
        )

    validate_geopackage(path)
    layer_names = {str(layer_info[0]) for layer_info in pyogrio.list_layers(path)}
    if layer not in layer_names:
        raise ValueError(
            f"{source_name} GeoPackage {path} has no required layer '{layer}'"
        )
    return wgpd.read_file(path, layer=layer)


def read_bestuurlijke_gebieden_layer(
    layer: str,
    *,
    year: int = DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
    path: Path | None = None,
) -> gpd.GeoDataFrame:
    """Read one raw layer from a downloaded yearly bestuurlijke gebieden source.

    Parameters
    ----------
    layer : str
        Source layer to read, such as ``landgebied`` or ``gemeentegebied``.
    year : int, optional
        Downloaded annual release to read. Defaults to the 2026 tile-source
        release.
    path : Path, optional
        Override for the downloaded GeoPackage path.

    Returns
    -------
    geopandas.GeoDataFrame
        Raw source fields and geometry from the requested layer.
    """
    source_path = path or bestuurlijke_gebieden_path(year)
    return _read_source_layer(
        source_path,
        layer=layer,
        source_name=f"Bestuurlijke gebieden {year}",
    )


def read_waterschapsgrenzen_layer(
    *,
    path: Path | None = None,
) -> gpd.GeoDataFrame:
    """Read the raw waterschap layer from the downloaded HWH GeoPackage."""
    source_path = path or _default_waterschapsgrenzen_path()
    return _read_source_layer(
        source_path,
        layer=WATERSCHAPSGRENZEN_LAYER,
        source_name="Waterschapsgrenzen",
    )


def read_landsgrens(
    *,
    year: int = DEFAULT_BESTUURLIJKE_GEBIEDEN_YEAR,
    path: Path | None = None,
) -> gpd.GeoDataFrame:
    """Read the national boundary from the downloaded landgebied layer.

    This function never downloads data. Use
    :func:`download_bestuurlijke_gebieden` before calling it when the source
    GeoPackage is not available locally.
    """
    return read_bestuurlijke_gebieden_layer(
        LANDSGRENS_LAYER,
        year=year,
        path=path,
    )


def _require_columns(
    gdf: gpd.GeoDataFrame,
    columns: Iterable[str],
    *,
    source_name: str,
) -> None:
    """Raise a clear error when an inspected source schema has changed."""
    missing = sorted(set(columns) - set(gdf.columns))
    if missing:
        raise ValueError(
            f"{source_name} source is missing required fields: {', '.join(missing)}"
        )


def _as_optional_code(value: object) -> str | None:
    """Normalize missing source code values to None without changing valid codes."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def parse_waterbeheercode_from_nen3610id(value: object) -> str | None:
    """Extract a waterbeheerder code from a NEN3610 identifier when available."""
    text = _as_optional_code(value)
    if text is None:
        return None
    match = NEN3610_WATERBEHEERCODE_PATTERN.match(text)
    if match is None:
        return None
    return match.group(1)


def normaliseer_bestuurlijke_gebieden(
    gebieden: gpd.GeoDataFrame,
    *,
    year: int,
) -> gpd.GeoDataFrame:
    """Normalize bestuurlijke gebieden while retaining the original source fields.

    The returned GeoDataFrame uses the uniform area model: ``naam``,
    ``bgt_code``, ``waterbeheercode``, ``bron``, ``versie``, and ``geometry``.
    Original PDOK fields, including ``identificatie`` and ``code``, remain
    available for traceability.
    """
    _require_columns(
        gebieden,
        ("naam", "code", "geometry"),
        source_name="Bestuurlijke gebieden",
    )
    logger.info(
        "Normalizing %s bestuurlijke gebieden for version %s", len(gebieden), year
    )
    result = gebieden.copy()
    result["bgt_code"] = result["code"].map(_as_optional_code)
    result["waterbeheercode"] = None
    result["bron"] = "PDOK Bestuurlijke Gebieden"
    result["versie"] = str(year)
    return result


def normaliseer_waterschapsgrenzen(
    gebieden: gpd.GeoDataFrame,
    *,
    version: str | None = None,
) -> gpd.GeoDataFrame:
    """Normalize waterschapsgrenzen and recover missing waterbeheercodes.

    The HWH source fields ``code``, ``waterbeheerdercode``, and ``nen3610id``
    are retained. ``waterbeheerdercode`` is exposed as the meaningful uniform
    ``waterbeheercode``. When that source value is missing, a code is parsed
    only from a NEN3610 ID in the form ``NL.WBHCODE.<code>.<type>.<id>``.
    """
    _require_columns(
        gebieden,
        ("naam", "code", "waterbeheerdercode", "nen3610id", "geometry"),
        source_name="Waterschapsgrenzen",
    )
    logger.info("Normalizing %s waterschapsgrenzen", len(gebieden))
    result = gebieden.copy()
    result["bgt_code"] = result["code"].map(_as_optional_code)
    result["waterbeheercode"] = result["waterbeheerdercode"].map(_as_optional_code)
    missing_codes = result["waterbeheercode"].isna()
    for index in result.index[missing_codes]:
        nen3610id = result.at[index, "nen3610id"]
        parsed_code = parse_waterbeheercode_from_nen3610id(nen3610id)
        if parsed_code is None:
            logger.warning(
                "Waterschapsgrens %s has no waterbeheercode and NEN3610 ID %r "
                "cannot be parsed",
                result.at[index, "naam"],
                nen3610id,
            )
            continue
        logger.warning(
            "Waterschapsgrens %s has no waterbeheercode; using %s parsed from "
            "NEN3610 ID %s",
            result.at[index, "naam"],
            parsed_code,
            nen3610id,
        )
        result.at[index, "waterbeheercode"] = parsed_code

    result["bron"] = "HWH Waterschappen Waterschapsgrenzen IMSO"
    result["versie"] = version
    return result
