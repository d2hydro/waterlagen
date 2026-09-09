"""Prepare and persist the first vector-only watersysteem step."""

import os
import tempfile
from pathlib import Path

import geopandas as gpd

from waterlagen import datastore
from waterlagen._crs import read_layer_crs_info, same_crs
from waterlagen._downloads import validate_geopackage
from waterlagen._geopackage import write_geopackage_layer
from waterlagen.datastore import DataStore
from waterlagen.logger import get_logger
from waterlagen.settings import settings

from .lines import (
    WatersysteemResult,
    create_hydroobject_verbindingen,
    split_hydroobjecten_at_points,
    split_hydroobjecten_by_length,
)

logger = get_logger(__name__)

DEFAULT_OUTPUT_FILENAME = "watersysteem.gpkg"
OUTPUT_LAYERS = (
    "hydroobject_primair",
    "hydroobject_secundair",
    "hydroobject_secundair_niet_verbonden",
    "hydroobject_segment",
    "hydroobject_verbinding",
)


def prepare_watersysteem(
    hydroobjecten: gpd.GeoDataFrame,
    puntobjecten: gpd.GeoDataFrame,
    *,
    tolerance: float = 2.0,
    max_length: float = 500.0,
    hydroobject_secundair: gpd.GeoDataFrame | None = None,
) -> WatersysteemResult:
    """Prepare primary hydroobjecten and final segment connections.

    This function only performs geometric and topological preparation. It does
    not read a GeoPackage, download source data, or write output. Input CRS
    values are required and are explicitly transformed to ``settings.crs`` by
    the underlying geometry helpers. Hydroobjecten are split first at nearby
    pointobjects and then into segments no longer than ``max_length``.

    Parameters
    ----------
    hydroobjecten : geopandas.GeoDataFrame
        Primary HyDAMO LineString or MultiLineString features. A missing
        ``bron_id`` is safely derived from ``globalid``, ``code``, or index.
    puntobjecten : geopandas.GeoDataFrame
        Point features that may split or connect primary hydroobjecten. Relevant
        point fields are retained on resulting connection records where a point
        causes a cross-source connection.
    tolerance : float, optional
        Maximum point-to-line distance in project-CRS units. Must be at least
        zero.
    max_length : float, optional
        Maximum resulting hydroobject segment length in project-CRS units. Must
        be greater than zero.
    hydroobject_secundair : geopandas.GeoDataFrame, optional
        Retained for backwards compatibility. Secondary objects are classified
        from their full geometry while writing and are not included in primary
        segment connections.

    Returns
    -------
    WatersysteemResult
        ``hydroobject_segmenten`` contains stable ``bron_id`` and
        ``segment_id`` values. ``hydroobject_verbinding`` contains deterministic
        directed relations between final segment IDs, their source ``bron_id``
        values, and relevant point attributes.
    """
    if tolerance < 0:
        raise ValueError("tolerance must not be negative")
    if max_length <= 0:
        raise ValueError("max_length must be greater than zero")

    result_at_points = split_hydroobjecten_at_points(
        hydroobjecten,
        puntobjecten,
        tolerance=tolerance,
    )
    segmenten = split_hydroobjecten_by_length(
        result_at_points.hydroobject_segmenten,
        max_length=max_length,
    )
    verbindingen = create_hydroobject_verbindingen(
        segmenten,
        puntobjecten,
        tolerance=tolerance,
    )
    logger.info(
        "Prepared watersysteem from %s primary hydroobjecten to %s primary segments and %s connections",
        len(hydroobjecten),
        len(segmenten),
        len(verbindingen),
    )
    return WatersysteemResult(
        hydroobject_segmenten=segmenten,
        hydroobject_verbinding=verbindingen,
    )


def _to_project_crs(features: gpd.GeoDataFrame, *, layer_name: str) -> gpd.GeoDataFrame:
    """Require and normalize an output layer CRS to the configured project CRS."""
    if features.crs is None:
        raise ValueError(f"{layer_name} has no CRS")
    if same_crs(features.crs, settings.crs):
        return features.copy()
    logger.info(
        "Transforming output layer %s from %s to %s",
        layer_name,
        features.crs,
        settings.crs,
    )
    return features.to_crs(settings.crs)


def _temporary_output_path(output_path: Path) -> Path:
    """Create an unused temporary GeoPackage path beside its target."""
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".gpkg",
        dir=output_path.parent,
    )
    os.close(fd)
    temporary_path = Path(temporary_name)
    temporary_path.unlink(missing_ok=True)
    return temporary_path


def _validate_watersysteem_output(path: Path) -> None:
    """Validate the required layers and their project CRS before replacement."""
    validate_geopackage(path)
    layers = {info.layer: info for info in read_layer_crs_info(path)}
    missing_layers = set(OUTPUT_LAYERS) - set(layers)
    if missing_layers:
        raise ValueError(
            "Watersysteem output is missing layers: "
            f"{', '.join(sorted(missing_layers))}"
        )
    for layer_name in OUTPUT_LAYERS:
        layer_info = layers[layer_name]
        if not layer_info.is_spatial:
            raise ValueError(f"Watersysteem layer '{layer_name}' is not spatial")
        if layer_info.crs is None or not same_crs(layer_info.crs, settings.crs):
            raise ValueError(
                f"Watersysteem layer '{layer_name}' does not use {settings.crs}"
            )


def _bron_ids(features: gpd.GeoDataFrame, *, layer_name: str) -> set[str]:
    """Return unique source IDs or raise when they cannot identify features."""
    if features.empty:
        return set()
    if "bron_id" not in features.columns:
        logger.warning("Layer %s has no bron_id column", layer_name)
        raise ValueError(f"{layer_name} has no bron_id column")

    identifiers = features["bron_id"]
    missing = identifiers.isna() | identifiers.astype(str).str.strip().eq("")
    if missing.any():
        logger.warning(
            "Layer %s has %s features without a usable bron_id",
            layer_name,
            int(missing.sum()),
        )
        raise ValueError(f"{layer_name} has features without a usable bron_id")

    normalized = identifiers.astype(str)
    duplicates = normalized.duplicated(keep=False)
    if duplicates.any():
        duplicate_ids = sorted(normalized.loc[duplicates].unique())
        logger.warning(
            "Layer %s has duplicate bron_id values: %s",
            layer_name,
            ", ".join(duplicate_ids),
        )
        raise ValueError(f"{layer_name} has duplicate bron_id values")
    return set(normalized)


def _secondary_positions_connected_to_primary(
    hydroobject_secundair: gpd.GeoDataFrame,
    hydroobject_primair: gpd.GeoDataFrame,
    *,
    tolerance: float,
) -> set[int]:
    """Return secondary positions in components that spatially reach a primary."""
    secondary_index = hydroobject_secundair.sindex
    primary_index = None
    if not hydroobject_primair.empty:
        primary_index = hydroobject_primair.sindex

    parents = list(range(len(hydroobject_secundair)))
    ranks = [0] * len(hydroobject_secundair)

    def find(position: int) -> int:
        root = position
        while parents[root] != root:
            root = parents[root]
        while parents[position] != position:
            parent = parents[position]
            parents[position] = root
            position = parent
        return root

    def union(first_position: int, second_position: int) -> None:
        first_root = find(first_position)
        second_root = find(second_position)
        if first_root == second_root:
            return
        if ranks[first_root] < ranks[second_root]:
            parents[first_root] = second_root
            return
        parents[second_root] = first_root
        if ranks[first_root] == ranks[second_root]:
            ranks[first_root] += 1

    directly_connected_positions: set[int] = set()
    for secondary_position, geometry in enumerate(hydroobject_secundair.geometry):
        if geometry is None or geometry.is_empty:
            continue
        query_geometry = geometry if tolerance == 0 else geometry.buffer(tolerance)

        if primary_index is not None:
            primary_positions = primary_index.query(
                query_geometry,
                predicate="intersects",
            )
            for primary_position in primary_positions:
                primary_geometry = hydroobject_primair.geometry.iloc[primary_position]
                if geometry.distance(primary_geometry) <= tolerance:
                    directly_connected_positions.add(secondary_position)
                    break

        secondary_positions = secondary_index.query(
            query_geometry,
            predicate="intersects",
        )
        for candidate_position in secondary_positions:
            if candidate_position <= secondary_position:
                continue
            candidate_geometry = hydroobject_secundair.geometry.iloc[candidate_position]
            if geometry.distance(candidate_geometry) <= tolerance:
                union(secondary_position, candidate_position)

    connected_component_roots = {
        find(position) for position in directly_connected_positions
    }
    return {
        position
        for position in range(len(hydroobject_secundair))
        if find(position) in connected_component_roots
    }


def split_connected_secondary_hydroobjecten(
    hydroobject_secundair: gpd.GeoDataFrame,
    hydroobject_primair: gpd.GeoDataFrame,
    hydroobject_verbinding: gpd.GeoDataFrame,
    *,
    tolerance: float = 2.0,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Split secondary hydroobjecten into connected and unconnected sources.

    Secondary hydroobjecten form spatially connected components. A component
    is connected only when at least one member lies within ``tolerance`` of a
    primary hydroobject; a component consisting solely of secondary objects is
    unconnected. Comparisons include vertices and every position along a line
    segment, so they do not depend on endpoint-based
    ``hydroobject_verbinding`` records. Those records are retained as an
    argument for API compatibility and are inspected only to warn about
    unknown source identifiers.

    Parameters
    ----------
    hydroobject_secundair : geopandas.GeoDataFrame
        Original selected secondary hydroobjecten with unique, non-empty
        ``bron_id`` values.
    hydroobject_primair : geopandas.GeoDataFrame
        Original selected primary hydroobjecten with unique, non-empty
        ``bron_id`` values.
    hydroobject_verbinding : geopandas.GeoDataFrame
        Existing directed connection layer. It does not determine the spatial
        classification.
    tolerance : float, optional
        Maximum distance in metres in the configured project CRS, by default
        2. Must be at least zero.

    Returns
    -------
    tuple[geopandas.GeoDataFrame, geopandas.GeoDataFrame]
        Connected secondary hydroobjecten followed by unconnected secondary
        hydroobjecten. Both preserve the input schema, order, and CRS.

    Raises
    ------
    ValueError
        If a non-empty source layer has missing or duplicate ``bron_id`` values,
        or ``tolerance`` is negative.
    """
    if hydroobject_secundair.empty:
        logger.info("Classified 0 secondary hydroobjecten: 0 connected, 0 unconnected")
        return hydroobject_secundair.copy(), hydroobject_secundair.copy()
    if tolerance < 0:
        raise ValueError("tolerance must not be negative")

    secundaire_ids = _bron_ids(
        hydroobject_secundair,
        layer_name="hydroobject_secundair",
    )
    primaire_ids = _bron_ids(
        hydroobject_primair,
        layer_name="hydroobject_primair",
    )
    overlapping_ids = secundaire_ids.intersection(primaire_ids)
    if overlapping_ids:
        logger.warning(
            "Primary and secondary hydroobjecten share bron_id values: %s",
            ", ".join(sorted(overlapping_ids)),
        )
        raise ValueError("primary and secondary hydroobjecten share bron_id values")
    required_columns = {"van_bron_id", "naar_bron_id"}
    missing_columns = required_columns - set(hydroobject_verbinding.columns)
    known_ids = primaire_ids.union(secundaire_ids)
    if hydroobject_verbinding.empty:
        pass
    elif missing_columns:
        logger.warning(
            "Ignoring hydroobject connections without source-ID columns: %s",
            ", ".join(sorted(missing_columns)),
        )
    else:
        for _, verbinding in hydroobject_verbinding.iterrows():
            connection_ids = {
                str(verbinding["van_bron_id"]),
                str(verbinding["naar_bron_id"]),
            }
            unknown_ids = connection_ids - known_ids
            if unknown_ids:
                logger.warning(
                    "Ignoring hydroobject connection with unknown bron_id values: %s",
                    ", ".join(sorted(unknown_ids)),
                )

    secundair_in_project_crs = _to_project_crs(
        hydroobject_secundair,
        layer_name="hydroobject_secundair",
    )
    primair_in_project_crs = _to_project_crs(
        hydroobject_primair,
        layer_name="hydroobject_primair",
    )
    connected_positions = _secondary_positions_connected_to_primary(
        secundair_in_project_crs,
        primair_in_project_crs,
        tolerance=tolerance,
    )
    connected = hydroobject_secundair.iloc[sorted(connected_positions)].copy()
    unconnected_positions = sorted(
        set(range(len(hydroobject_secundair))) - connected_positions
    )
    unconnected = hydroobject_secundair.iloc[unconnected_positions].copy()
    logger.info(
        "Classified %s secondary hydroobjecten: %s connected, %s unconnected",
        len(hydroobject_secundair),
        len(connected),
        len(unconnected),
    )
    return connected, unconnected


def write_watersysteem(
    *,
    hydroobject_primair: gpd.GeoDataFrame,
    hydroobject_secundair: gpd.GeoDataFrame,
    watersysteem: WatersysteemResult,
    data_store: DataStore | None = None,
    output_path: Path | None = None,
    overwrite: bool = False,
    secondary_connection_tolerance: float = 2.0,
) -> Path:
    """Atomically write the prepared watersysteem layers to a GeoPackage.

    Existing output is reused only when it passes the required GeoPackage,
    layer, and CRS validation. A failed write or validation removes its
    temporary file and leaves an existing target untouched. Layers with a
    bundled QML style register that style in the GeoPackage automatically.

    Parameters
    ----------
    hydroobject_primair : geopandas.GeoDataFrame
        Selected primary source hydroobjecten. Written without topology changes.
    hydroobject_secundair : geopandas.GeoDataFrame
        Selected secondary source hydroobjecten. They are divided into connected
        and unconnected output layers using their complete line geometry.
    watersysteem : WatersysteemResult
        Geometrically prepared primary segments and point-induced connections.
    data_store : DataStore, optional
        Supplies the default output directory.
    output_path : Path, optional
        Override for the target GeoPackage. Defaults to
        ``datastore.afwateringseenheden_path / 'watersysteem.gpkg'``.
    overwrite : bool, optional
        Whether to replace an existing valid GeoPackage. With ``False``, a
        valid target is reused; an invalid target is replaced only after a new
        temporary GeoPackage has been validated.
    secondary_connection_tolerance : float, optional
        Maximum distance in metres between complete primary and secondary
        hydroobject geometries when classifying connected secondary objects, by
        default 2.

    Returns
    -------
    Path
        Validated GeoPackage with exactly the required output layers.
    """
    data_store = data_store or datastore
    output_path = Path(
        output_path or data_store.afwateringseenheden_path / DEFAULT_OUTPUT_FILENAME
    )
    if output_path.exists() and not overwrite:
        try:
            _validate_watersysteem_output(output_path)
        except Exception as exc:
            logger.warning(
                "Existing watersysteem output %s is invalid and will be replaced: %s",
                output_path,
                exc,
            )
        else:
            logger.info("Reusing existing validated watersysteem at %s", output_path)
            return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    secundair_verbonden, secundair_niet_verbonden = (
        split_connected_secondary_hydroobjecten(
            hydroobject_secundair,
            hydroobject_primair,
            watersysteem.hydroobject_verbinding,
            tolerance=secondary_connection_tolerance,
        )
    )
    layers = (
        ("hydroobject_primair", hydroobject_primair),
        ("hydroobject_secundair", secundair_verbonden),
        ("hydroobject_secundair_niet_verbonden", secundair_niet_verbonden),
        ("hydroobject_segment", watersysteem.hydroobject_segmenten),
        ("hydroobject_verbinding", watersysteem.hydroobject_verbinding),
    )
    normalized_layers = [
        (_layer_name, _to_project_crs(features, layer_name=_layer_name))
        for _layer_name, features in layers
    ]
    temporary_path = _temporary_output_path(output_path)
    try:
        for index, (layer_name, features) in enumerate(normalized_layers):
            logger.info(
                "Writing watersysteem layer %s with %s features",
                layer_name,
                len(features),
            )
            write_geopackage_layer(
                features,
                temporary_path,
                mode="w" if index == 0 else "a",
                layer_name=layer_name,
            )
        logger.info("Validating temporary watersysteem GeoPackage %s", temporary_path)
        _validate_watersysteem_output(temporary_path)
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    logger.info("Wrote watersysteem layers %s to %s", OUTPUT_LAYERS, output_path)
    return output_path
