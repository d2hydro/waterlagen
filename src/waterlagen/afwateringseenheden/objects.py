"""Read and select HyDAMO source objects for the watersysteem workflow."""

from collections.abc import Collection, Iterable, Mapping
from pathlib import Path
import re

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely import force_2d
from shapely.geometry import LineString, MultiLineString, Point
from shapely.geometry.base import BaseGeometry

from waterlagen import _geopandas as wgpd
from waterlagen._crs import format_crs, same_crs
from waterlagen.logger import get_logger
from waterlagen.settings import settings

logger = get_logger(__name__)

WATERBEHEERCODE_COLUMN = "nen3610id"
WATERBEHEERCODE_PATTERN = re.compile(r"^NL\.WBHCODE\.([^.]+)\.")
CATEGORIE_OPPERVLAKTEWATER_COLUMN = "categorieoppwaterlichaam"
ATTRIBUTE_FILTER_ALIASES = {
    "categorieoppervlaktewater": CATEGORIE_OPPERVLAKTEWATER_COLUMN,
}
RELEVANT_FIELDS: dict[str, tuple[str, ...]] = {
    "hydroobject": (
        "code",
        "globalid",
        "naam",
        "nen3610id",
        CATEGORIE_OPPERVLAKTEWATER_COLUMN,
        "statusleggerwatersysteem",
        "statusobject",
    ),
    "gemaal": (
        "code",
        "globalid",
        "naam",
        "nen3610id",
        "functiegemaal",
        "maximalecapaciteit",
        "statusleggerwatersysteem",
        "statusobject",
    ),
    "stuw": (
        "code",
        "globalid",
        "naam",
        "nen3610id",
        "hoofdfunctiestuw",
        "typestuw",
        "statusleggerwatersysteem",
        "statusobject",
    ),
}
DEFAULT_RELEVANT_FIELDS = ("code", "globalid", "naam", WATERBEHEERCODE_COLUMN)


def _normaliseer_waterbeheercode(value: object) -> str | None:
    """Convert a source or requested code to a comparable string value."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


def _gevraagde_waterbeheercodes(
    waterbeheercodes: Iterable[str | int | float | None] | None,
) -> set[str] | None:
    """Normalize an optional waterbeheerder-code filter."""
    if waterbeheercodes is None:
        return None
    if isinstance(waterbeheercodes, str):
        values: Iterable[object] = (waterbeheercodes,)
    else:
        values = waterbeheercodes

    codes = {
        code
        for value in values
        if (code := _normaliseer_waterbeheercode(value)) is not None
    }
    if not codes:
        raise ValueError("waterbeheercodes contains no usable code values")
    return codes


def waterbeheercode_from_nen3610id(value: object) -> str | None:
    """Extract the waterbeheerder code from a HyDAMO NEN3610 identifier."""
    identifier = _normaliseer_waterbeheercode(value)
    if identifier is None:
        return None
    match = WATERBEHEERCODE_PATTERN.match(identifier)
    if match is None:
        return None
    return match.group(1)


def _selection_geometry_in_source_crs(
    spatial_selection: BaseGeometry,
    *,
    selection_crs: str | int,
    source_crs: str | int,
) -> BaseGeometry:
    """Transform a non-empty selection geometry to the source CRS."""
    if spatial_selection.is_empty:
        raise ValueError("spatial_selection must not be empty")
    if same_crs(selection_crs, source_crs):
        return spatial_selection
    selection = gpd.GeoSeries([spatial_selection], crs=selection_crs)
    return selection.to_crs(source_crs).iloc[0]


def _attribute_filter_columns(
    attribute_filters: Mapping[str, Collection[object]] | None,
) -> dict[str, Collection[object]]:
    """Map documented filter names to explicit HyDAMO source column names."""
    if attribute_filters is None:
        return {}
    return {
        ATTRIBUTE_FILTER_ALIASES.get(column, column): values
        for column, values in attribute_filters.items()
    }


def _add_waterbeheercode(
    features: gpd.GeoDataFrame,
    *,
    layer: str,
) -> gpd.GeoDataFrame:
    """Add parsed waterbeheercodes and warn for source values that cannot be used."""
    result = features.copy()
    if WATERBEHEERCODE_COLUMN not in result.columns:
        result["waterbeheercode"] = None
    else:
        result["waterbeheercode"] = result[WATERBEHEERCODE_COLUMN].map(
            waterbeheercode_from_nen3610id
        )

    missing_code_count = int(result["waterbeheercode"].isna().sum())
    if missing_code_count:
        logger.warning(
            "HyDAMO layer %s contains %s selected features without a parseable "
            "waterbeheercode in %s",
            layer,
            missing_code_count,
            WATERBEHEERCODE_COLUMN,
        )
    return result


def _apply_attribute_filters(
    features: gpd.GeoDataFrame,
    *,
    layer: str,
    attribute_filters: Mapping[str, Collection[object]] | None,
) -> gpd.GeoDataFrame:
    """Apply exact source-value filters and log every reduction."""
    result = features
    for column, values in _attribute_filter_columns(attribute_filters).items():
        if column not in result.columns:
            raise ValueError(
                f"HyDAMO layer '{layer}' has no '{column}' column required for "
                "attribute_filters"
            )
        before_count = len(result)
        if isinstance(values, str):
            accepted_values: Collection[object] = (values,)
        else:
            accepted_values = values
        result = result[result[column].isin(accepted_values)].copy()
        logger.info(
            "Applied HyDAMO %s attribute filter %s: %s to %s features",
            layer,
            column,
            before_count,
            len(result),
        )
    return result


def _add_bron_id(features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add a stable source identifier using globalid, code, or the row index."""
    result = features.copy()
    identifiers: list[str] = []
    for index, row in result.iterrows():
        for column in ("globalid", "code"):
            value = row.get(column)
            if value is not None and not pd.isna(value) and str(value).strip():
                identifiers.append(str(value))
                break
        else:
            identifiers.append(str(index))
    result["bron_id"] = identifiers
    return result


def _to_2d(features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop Z coordinates from source geometry while retaining its CRS."""
    result = features.copy()
    result.geometry = result.geometry.map(
        lambda geometry: force_2d(geometry) if geometry is not None else None
    )
    return result


def _read_hydamo_layer(
    hydamo_path: Path,
    *,
    layer: str,
    spatial_selection: BaseGeometry | None,
    waterbeheercodes: Iterable[str | int | float | None] | None,
    attribute_filters: Mapping[str, Collection[object]] | None,
    spatial_selection_crs: str | int,
) -> gpd.GeoDataFrame:
    """Read one local HyDAMO layer, select it, and return it in the project CRS."""
    hydamo_path = Path(hydamo_path)
    if not hydamo_path.exists():
        raise FileNotFoundError(
            f"HyDAMO GeoPackage is missing: {hydamo_path}. "
            "Download it first with waterlagen.hydamo.download_hydamo()."
        )

    requested_codes = _gevraagde_waterbeheercodes(waterbeheercodes)
    layer_info = pyogrio.read_info(hydamo_path, layer=layer)
    source_crs = layer_info.get("crs")
    if source_crs is None:
        raise ValueError(f"HyDAMO layer '{layer}' has no CRS")

    available_fields = set(layer_info["fields"])
    filter_columns = _attribute_filter_columns(attribute_filters)
    for column in filter_columns:
        if column not in available_fields:
            raise ValueError(
                f"HyDAMO layer '{layer}' has no '{column}' column required for "
                "attribute_filters"
            )
    if requested_codes is not None and WATERBEHEERCODE_COLUMN not in available_fields:
        raise ValueError(
            f"HyDAMO layer '{layer}' has no '{WATERBEHEERCODE_COLUMN}' column "
            "required for waterbeheercodes filtering"
        )

    fields = [
        field
        for field in RELEVANT_FIELDS.get(layer, DEFAULT_RELEVANT_FIELDS)
        if field in available_fields
    ]
    fields.extend(column for column in filter_columns if column not in fields)
    fields = list(dict.fromkeys(fields))

    source_selection = None
    read_kwargs: dict[str, object] = {"layer": layer, "columns": fields}
    if spatial_selection is not None:
        source_selection = _selection_geometry_in_source_crs(
            spatial_selection,
            selection_crs=spatial_selection_crs,
            source_crs=source_crs,
        )
        read_kwargs["bbox"] = source_selection.bounds
        logger.info(
            "Reading HyDAMO %s with spatial selection in %s",
            layer,
            format_crs(source_crs),
        )
    else:
        logger.info("Reading all HyDAMO %s features", layer)

    features = wgpd.read_file(hydamo_path, **read_kwargs)
    if source_selection is not None:
        features = features[features.geometry.intersects(source_selection)].copy()
    if features.crs is None:
        raise ValueError(f"HyDAMO layer '{layer}' has no CRS")
    if not same_crs(features.crs, settings.crs):
        features = features.to_crs(settings.crs)
    features = _to_2d(features)

    features = _add_waterbeheercode(features, layer=layer)
    if requested_codes is not None:
        before_count = len(features)
        features = features[features["waterbeheercode"].isin(requested_codes)].copy()
        logger.info(
            "Applied HyDAMO %s waterbeheercodes %s: %s to %s features",
            layer,
            sorted(requested_codes),
            before_count,
            len(features),
        )
    features = _apply_attribute_filters(
        features,
        layer=layer,
        attribute_filters=attribute_filters,
    )
    logger.info("Read %s HyDAMO %s features", len(features), layer)
    return features.reset_index(drop=True)


def read_hydroobjecten(
    hydamo_path: Path,
    *,
    spatial_selection: BaseGeometry | None = None,
    waterbeheercodes: Iterable[str | int | float | None] | None = None,
    attribute_filters: Mapping[str, Collection[object]] | None = None,
    spatial_selection_crs: str | int = settings.crs,
) -> gpd.GeoDataFrame:
    """Read selected HyDAMO hydroobjecten as project-CRS line features.

    MultiLineStrings are exploded while preserving relevant source attributes.
    Empty, invalid, and non-line geometries are skipped with a warning. The
    returned data includes ``bron_id`` from ``globalid`` where available,
    otherwise ``code`` or the source row index.

    Parameters
    ----------
    hydamo_path : Path
        Local HyDAMO GeoPackage containing the ``hydroobject`` layer.
    spatial_selection : BaseGeometry, optional
        Selection geometry in ``spatial_selection_crs``. ``None`` reads the
        complete source layer.
    waterbeheercodes : Iterable[str | int | float | None], optional
        Optional codes parsed from the source ``nen3610id`` field.
    attribute_filters : Mapping[str, Collection[object]], optional
        Exact source-value filters. The documented alias
        ``categorieoppervlaktewater`` maps to the actual HyDAMO column
        ``categorieoppwaterlichaam``.
    spatial_selection_crs : str | int, optional
        CRS of ``spatial_selection``. Results always use ``settings.crs``.

    Returns
    -------
    geopandas.GeoDataFrame
        Selected LineString features with source attributes, ``bron_id``, and
        normalized ``waterbeheercode`` in the configured project CRS.
    """
    source = _read_hydamo_layer(
        hydamo_path,
        layer="hydroobject",
        spatial_selection=spatial_selection,
        waterbeheercodes=waterbeheercodes,
        attribute_filters=attribute_filters,
        spatial_selection_crs=spatial_selection_crs,
    )
    records: list[dict[str, object]] = []
    for index, row in source.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty or not geometry.is_valid:
            logger.warning("Skipping invalid or empty hydroobject at index %s", index)
            continue
        if isinstance(geometry, MultiLineString):
            logger.warning("Exploding MultiLineString hydroobject at index %s", index)
            geometries = geometry.geoms
        elif isinstance(geometry, LineString):
            geometries = (geometry,)
        else:
            logger.warning(
                "Skipping hydroobject at index %s with geometry type %s",
                index,
                geometry.geom_type,
            )
            continue
        for line in geometries:
            if line.is_empty or line.length == 0:
                logger.warning("Skipping empty hydroobject line at index %s", index)
                continue
            record = row.drop(labels="geometry").to_dict()
            record["geometry"] = line
            records.append(record)

    if not records:
        result = source.iloc[0:0].copy()
    else:
        result = gpd.GeoDataFrame(records, geometry="geometry", crs=source.crs)
    return _add_bron_id(result).reset_index(drop=True)


def read_puntobjecten(
    hydamo_path: Path,
    *,
    layers: Iterable[str] = ("gemaal", "stuw"),
    spatial_selection: BaseGeometry | None = None,
    waterbeheercodes: Iterable[str | int | float | None] | None = None,
    attribute_filters: Mapping[str, Collection[object]] | None = None,
    spatial_selection_crs: str | int = settings.crs,
) -> gpd.GeoDataFrame:
    """Read selected HyDAMO point layers and combine them into one GeoDataFrame.

    Every retained point has an ``objecttype`` containing its source-layer name
    and a stable ``bron_id``. Empty, invalid, and non-point geometries are
    skipped with warnings. All source layers are converted to ``settings.crs``
    before combining them.

    Parameters
    ----------
    hydamo_path : Path
        Local HyDAMO GeoPackage containing the requested point layers.
    layers : Iterable[str], optional
        Source layer names. Defaults to ``gemaal`` and ``stuw``.
    spatial_selection : BaseGeometry, optional
        Selection geometry in ``spatial_selection_crs``. ``None`` reads each
        complete source layer.
    waterbeheercodes : Iterable[str | int | float | None], optional
        Optional codes parsed from source ``nen3610id`` fields.
    attribute_filters : Mapping[str, Collection[object]], optional
        Exact source-value filters with the documented source-column aliases.
    spatial_selection_crs : str | int, optional
        CRS of ``spatial_selection``. Results always use ``settings.crs``.

    Returns
    -------
    geopandas.GeoDataFrame
        Combined point features with ``objecttype``, ``bron_id``, relevant
        source fields, and normalized ``waterbeheercode``.
    """
    layer_names = tuple(layers)
    if not layer_names:
        raise ValueError("layers must contain at least one HyDAMO point layer")

    point_layers: list[gpd.GeoDataFrame] = []
    for layer in layer_names:
        source = _read_hydamo_layer(
            hydamo_path,
            layer=layer,
            spatial_selection=spatial_selection,
            waterbeheercodes=waterbeheercodes,
            attribute_filters=attribute_filters,
            spatial_selection_crs=spatial_selection_crs,
        )
        records: list[dict[str, object]] = []
        for index, row in source.iterrows():
            geometry = row.geometry
            if geometry is None or geometry.is_empty or not geometry.is_valid:
                logger.warning(
                    "Skipping invalid or empty %s point object at index %s",
                    layer,
                    index,
                )
                continue
            if not isinstance(geometry, Point):
                logger.warning(
                    "Skipping %s object at index %s with geometry type %s",
                    layer,
                    index,
                    geometry.geom_type,
                )
                continue
            record = row.drop(labels="geometry").to_dict()
            record["objecttype"] = layer
            record["geometry"] = geometry
            records.append(record)
        if records:
            point_layers.append(
                _add_bron_id(
                    gpd.GeoDataFrame(records, geometry="geometry", crs=source.crs)
                )
            )

    if not point_layers:
        return gpd.GeoDataFrame(
            {
                "objecttype": pd.Series(dtype="object"),
                "bron_id": pd.Series(dtype="object"),
                "waterbeheercode": pd.Series(dtype="object"),
            },
            geometry=gpd.GeoSeries([], crs=settings.crs),
            crs=settings.crs,
        )
    combined = gpd.GeoDataFrame(
        pd.concat(point_layers, ignore_index=True),
        geometry="geometry",
        crs=settings.crs,
    )
    logger.info(
        "Combined %s HyDAMO point objects from layers %s",
        len(combined),
        layer_names,
    )
    return combined
