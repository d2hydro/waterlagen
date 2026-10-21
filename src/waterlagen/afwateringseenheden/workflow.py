"""Prepare and persist the first vector-only watersysteem step."""

import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

import geopandas as gpd

from waterlagen import datastore
from waterlagen._crs import read_layer_crs_info, same_crs
from waterlagen._downloads import validate_geopackage
from waterlagen._filesystem import replace_file
from waterlagen._geopackage import (
    write_geopackage_layer,
    write_geopackage_layer_atomically,
)
from waterlagen._geopandas import read_file
from waterlagen.datastore import DataStore
from waterlagen.logger import get_logger
from waterlagen.settings import settings

from .duikers import (
    _classify_adjacent,
    _frame_identity,
    _prepare_culverts,
    _validate_culvert_options,
)
from .lines import (
    WatersysteemResult,
    _ensure_bron_id,
    _prepare_hydroobjecten,
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
    duikersifonhevel: gpd.GeoDataFrame | None = None,
    hydroobject_primair: gpd.GeoDataFrame | None = None,
    duiker_tolerance: float = 0.5,
    max_aansluitlengte: float | None = None,
) -> WatersysteemResult:
    """Prepare primary hydroobjecten and final segment connections.

    This function only performs geometric and topological preparation. It does
    not read a GeoPackage, download source data, or write output. Input CRS
    values are required and are explicitly transformed to ``settings.crs`` by
    the underlying geometry helpers. Optional culvert routes are matched against
    the full primary context. Culvert and nearby point-object boundaries precede
    the split into segments no longer than ``max_length``.

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
    duikersifonhevel : geopandas.GeoDataFrame, optional
        Culverts from all selected authorities. None preserves the legacy
        workflow. Supplied culverts always exclude matched routes from primary
        burning and drainage targets; unsuccessful matches become controls.
    hydroobject_primair : geopandas.GeoDataFrame, optional
        Full primary context for culvert matching, independent of target mode.
        Defaults to ``hydroobjecten``. Target selection uses ``bron_id``.
    duiker_tolerance : float, optional
        Inclusive endpoint matching distance, default 0.5 metres. Independent
        of the general network tolerance; finite and non-negative.
    max_aansluitlengte : float, optional
        Exclude direct adjoining physical pieces at or below this length from
        targets only, before maximum-length splitting. None retains them all;
        zero is valid. Must be finite and non-negative.

    Returns
    -------
    WatersysteemResult
        ``hydroobject_segmenten`` contains stable ``bron_id`` and
        ``segment_key`` values. ``hydroobject_verbinding`` contains deterministic
        directed relations between final segment IDs, their source ``bron_id``
        values, and relevant point attributes.
    """
    if tolerance < 0:
        raise ValueError("tolerance must not be negative")
    if max_length <= 0:
        raise ValueError("max_length must be greater than zero")

    _validate_culvert_options(duiker_tolerance, max_aansluitlengte)
    culverts = None
    lines = hydroobjecten
    if duikersifonhevel is not None:
        culverts = _prepare_culverts(
            hydroobjecten if hydroobject_primair is None else hydroobject_primair,
            duikersifonhevel,
            tolerance=duiker_tolerance,
        )
        lines = culverts.pieces
    result_at_points = split_hydroobjecten_at_points(
        lines,
        puntobjecten,
        tolerance=tolerance,
    )
    physical_pieces = result_at_points.hydroobject_segmenten
    if culverts is not None:
        # Only pre-existing source endpoints and physical point cuts may join
        # distinct sources. A coincident culvert cut must not remove those joins.
        original_pieces = split_hydroobjecten_at_points(
            culverts.primary,
            puntobjecten,
            tolerance=tolerance,
        ).hydroobject_segmenten
        physical_endpoints = {
            (row.bron_id, tuple(coordinate))
            for row in original_pieces.itertuples()
            for coordinate in (row.geometry.coords[0], row.geometry.coords[-1])
        }
        for column, endpoint in (("duiker_knip_start", 0), ("duiker_knip_eind", -1)):
            physical_pieces[column] = [
                bool(row[column])
                and (row.bron_id, tuple(row.geometry.coords[endpoint]))
                not in physical_endpoints
                for _, row in physical_pieces.iterrows()
            ]
        physical_pieces = _classify_adjacent(physical_pieces, max_aansluitlengte)
        targets = set(_ensure_bron_id(hydroobjecten).bron_id)
        physical_pieces = physical_pieces.loc[
            physical_pieces.bron_id.isin(targets)
        ].copy()
    segmenten = split_hydroobjecten_by_length(
        physical_pieces,
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
        hydroobject_primair_bron=culverts.primary if culverts is not None else None,
        hydroobject_primair_delen=culverts.pieces if culverts is not None else None,
        duiker_controle=culverts.controls if culverts is not None else None,
        duiker_signature=hashlib.sha256(
            json.dumps(
                {
                    "culverts": culverts.signature,
                    "targets": _frame_identity(hydroobjecten),
                    "points": _frame_identity(puntobjecten),
                    "tolerance": tolerance,
                    "max_length": max_length,
                    "max_aansluitlengte": max_aansluitlengte,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if culverts is not None
        else None,
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
    with closing(sqlite3.connect(path)) as connection:
        legacy_metadata = connection.execute(
            "SELECT name FROM sqlite_master WHERE name='waterlagen_duikers'"
        ).fetchone()
    if legacy_metadata is not None:
        raise ValueError(
            "Technical culvert metadata belongs in intern/, not this GeoPackage"
        )
    layers = {info.layer: info for info in read_layer_crs_info(path)}
    required_layers = OUTPUT_LAYERS
    missing_layers = set(required_layers) - set(layers)
    if missing_layers:
        raise ValueError(
            "Watersysteem output is missing layers: "
            f"{', '.join(sorted(missing_layers))}"
        )
    extra_layers = {
        name
        for name, info in layers.items()
        if info.is_spatial and name not in required_layers
    }
    if extra_layers:
        raise ValueError(
            f"Watersysteem contains inspection layers: {sorted(extra_layers)}"
        )
    for layer_name in required_layers:
        layer_info = layers[layer_name]
        if not layer_info.is_spatial:
            raise ValueError(f"Watersysteem layer '{layer_name}' is not spatial")
        if layer_info.crs is None or not same_crs(layer_info.crs, settings.crs):
            raise ValueError(
                f"Watersysteem layer '{layer_name}' does not use {settings.crs}"
            )


def _watersysteem_metadata(path: Path, signature: str | None) -> dict[str, str | None]:
    """Bind the preparation identity to the actual published GeoPackage."""
    with path.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    return {"signature": signature, "output_sha256": checksum}


def _write_watersysteem_metadata(path: Path, metadata: dict[str, str | None]) -> None:
    """Publish metadata only after the matching GeoPackage was replaced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".json",
            delete=False,
        ) as destination:
            temporary_path = Path(destination.name)
            json.dump(metadata, destination, indent=2)
        replace_file(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


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


def _connection_segment_ids(
    connections: gpd.GeoDataFrame, path: Path
) -> gpd.GeoDataFrame:
    """Link connection IDs to the actual segment FIDs written to this package."""
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            "SELECT segment_key, fid FROM hydroobject_segment"
        ).fetchall()
    identifiers = dict(rows)
    if len(identifiers) != len(rows):
        raise ValueError("Duplicate segment_key in hydroobject_segment")
    result = connections.copy()
    for direction in ("van", "naar"):
        values = result[f"{direction}_segment_key"].map(identifiers)
        if values.isna().any():
            raise ValueError(f"Unknown {direction}_segment in hydroobject_verbinding")
        result[f"{direction}_segment"] = values.astype("int64")
    result = result.rename(
        columns={
            "punt_bron_id": "kunstwerk_bron_id",
            "punt_code": "kunstwerk_code",
            "punt_naam": "kunstwerk_naam",
            "waterbeheercode": "kunstwerk_waterbeheercode",
        }
    )
    return result[
        [
            "van_segment",
            "naar_segment",
            "objecttype",
            "kunstwerk_bron_id",
            "kunstwerk_code",
            "kunstwerk_naam",
            "kunstwerk_waterbeheercode",
            "geometry",
        ]
    ]


def _validate_segment_numbers(path: Path) -> None:
    """Require compact connections with valid numeric segment references."""
    with closing(sqlite3.connect(path)) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(hydroobject_verbinding)")
        }
        obsolete = {
            "van_segment_key",
            "naar_segment_key",
            "van_bron_id",
            "naar_bron_id",
            "waterbeheercode",
            "punt_bron_id",
            "punt_code",
            "punt_naam",
            "punt_waterbeheercode",
        }
        if obsolete.intersection(columns) or "kunstwerk_waterbeheercode" not in columns:
            raise ValueError("Outdated hydroobject_verbinding schema")
        invalid = connection.execute(
            "SELECT COUNT(*) FROM hydroobject_segment "
            "WHERE segment_id IS NULL OR typeof(segment_id) != 'integer' OR segment_id != fid"
        ).fetchone()[0]
        if invalid:
            raise ValueError("segment_id must equal the stored integer segment FID")
        for direction in ("van", "naar"):
            invalid = connection.execute(
                f"SELECT COUNT(*) FROM hydroobject_verbinding AS v "
                f"LEFT JOIN hydroobject_segment AS s ON s.segment_id = v.{direction}_segment "
                f"WHERE s.fid IS NULL "
                f"OR typeof(v.{direction}_segment) != 'integer'"
            ).fetchone()[0]
            if invalid:
                raise ValueError(f"Invalid numeric {direction}_segment link")


def _write_inspection_layer(
    features: gpd.GeoDataFrame | None, path: Path, layer: str
) -> None:
    """Refresh one inspection layer, clearing stale rows when input is removed."""
    if features is None:
        if not path.exists() or layer not in set(gpd.list_layers(path)["name"]):
            return
        features = read_file(path, layer=layer).iloc[:0].copy()
    logger.info(
        "Writing inspection layer %s with %s features to %s", layer, len(features), path
    )
    write_geopackage_layer_atomically(
        features, path, layer_name=layer, preserve_other_layers=True
    )


def write_watersysteem(
    *,
    hydroobject_primair: gpd.GeoDataFrame,
    hydroobject_secundair: gpd.GeoDataFrame,
    watersysteem: WatersysteemResult,
    data_store: DataStore | None = None,
    output_path: Path | None = None,
    overwrite: bool = False,
    secondary_connection_tolerance: float = 2.0,
    hydroobject_zonder_categorie: gpd.GeoDataFrame | None = None,
    controle_path: Path | None = None,
) -> Path:
    """Atomically write the prepared watersysteem layers to a GeoPackage.

    Existing output is reused only when it passes the required GeoPackage,
    layer, and CRS validation. A failed write or validation removes its
    temporary file and leaves an existing target untouched. Layers with a
    bundled QML style register that style in the GeoPackage automatically.
    Connections include integer ``van_segment`` and ``naar_segment`` referencing
    the actual GeoPackage segment FIDs, also used by catchment ``segment_id``.
    These numbers are local to this output, unlike the source-based segment IDs.
    Source keys remain in the segment layer; connections omit duplicated keys.
    Optional structure attributes include ``kunstwerk_waterbeheercode``. Connections
    without a linked point object have null point attributes.

    Parameters
    ----------
    hydroobject_primair : geopandas.GeoDataFrame
        All selected primary burn-context lines, including non-target authorities.
        Used unchanged for the joint secondary test. With culvert preparation,
        retained in ``intern/watersysteem.gpkg`` while ``hydroobject_primair``
        contains only eligible burn pieces.
    hydroobject_secundair : geopandas.GeoDataFrame
        Selected secondary source hydroobjecten. They are divided into connected
        and unconnected output layers using their complete line geometry.
    watersysteem : WatersysteemResult
        Geometrically prepared participating primary targets and point-induced
        connections. These may be a subset of the primary burn context.
    data_store : DataStore, optional
        Supplies the default output directory.
    output_path : Path, optional
        Override for the target GeoPackage. Defaults to
        ``datastore.afwateringseenheden_path / 'watersysteem.gpkg'``.
    overwrite : bool, optional
        Whether to replace an existing valid GeoPackage. With ``False``, a
        valid target is reused; an invalid target is replaced only after a new
        temporary GeoPackage has been validated. With culverts, source contents,
        selection and settings must also match the stored preparation identity;
        otherwise the snapshot is regenerated, including control-only changes.
    secondary_connection_tolerance : float, optional
        Maximum distance in metres between complete primary and secondary
        hydroobject geometries when classifying connected secondary objects, by
        default 2.
    hydroobject_zonder_categorie : geopandas.GeoDataFrame, optional
        Excluded GKW lines without a category. Written to ``controle_path``,
        never included in burning or secondary connectivity.
    controle_path : pathlib.Path, optional
        Inspection GeoPackage, default ``output_path.parent/controle.gpkg``.
        Its ``duikersifonhevel`` layer is refreshed, including when empty or
        resuming; other inspection layers are preserved. Also stores source
        lines without a category. Removed inputs clear old inspection rows. Technical primary
        source and split layers are kept in ``intern/watersysteem.gpkg`` beside
        the output. Missing inspection files are rebuilt even on reuse.
        Culvert snapshots are reused only with matching input metadata.
        Preparation metadata is stored in ``intern/<output filename>.json``,
        tied to the output checksum. Missing or mismatching metadata causes
        regeneration rather than reuse.

    Returns
    -------
    Path
        Validated GeoPackage with exactly five spatial watersysteem layers.
    """
    data_store = data_store or datastore
    output_path = Path(
        output_path or data_store.afwateringseenheden_path / DEFAULT_OUTPUT_FILENAME
    )
    controle_path = Path(controle_path or output_path.parent / "controle.gpkg")
    metadata_path = output_path.parent / "intern" / f"{output_path.name}.json"
    signature = None
    if watersysteem.duiker_signature is not None:
        if (
            watersysteem.hydroobject_primair_bron is None
            or watersysteem.hydroobject_primair_delen is None
            or watersysteem.duiker_controle is None
        ):
            raise ValueError("Incomplete prepared culvert snapshot")
        if _frame_identity(
            _prepare_hydroobjecten(hydroobject_primair)
        ) != _frame_identity(watersysteem.hydroobject_primair_bron):
            raise ValueError("Primary input differs from the prepared culvert context")
        signature = hashlib.sha256(
            json.dumps(
                {
                    "prepared": watersysteem.duiker_signature,
                    "primary": _frame_identity(hydroobject_primair),
                    "secondary": _frame_identity(hydroobject_secundair),
                    "segments": _frame_identity(watersysteem.hydroobject_segmenten),
                    "primary_pieces": _frame_identity(
                        watersysteem.hydroobject_primair_delen
                    ),
                    "controls": _frame_identity(watersysteem.duiker_controle),
                    "connections": _frame_identity(watersysteem.hydroobject_verbinding),
                    "secondary_tolerance": secondary_connection_tolerance,
                    "missing_category": _frame_identity(hydroobject_zonder_categorie)
                    if hydroobject_zonder_categorie is not None
                    else None,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if not watersysteem.duiker_controle.empty:
            logger.warning(
                "%s duikers require inspection in %s (duikersifonhevel)",
                len(watersysteem.duiker_controle),
                controle_path,
            )
    internal_path = output_path.parent / "intern" / "watersysteem.gpkg"
    for features, path, layer in (
        (watersysteem.duiker_controle, controle_path, "duikersifonhevel"),
        (hydroobject_zonder_categorie, controle_path, "hydroobject_zonder_categorie"),
        (
            watersysteem.hydroobject_primair_bron,
            internal_path,
            "hydroobject_primair_bron",
        ),
        (
            watersysteem.hydroobject_primair_delen,
            internal_path,
            "hydroobject_primair_delen",
        ),
    ):
        _write_inspection_layer(features, path, layer)
    if output_path.exists() and not overwrite:
        try:
            _validate_watersysteem_output(output_path)
            _validate_segment_numbers(output_path)
            previous = json.loads(metadata_path.read_text(encoding="utf-8"))
            if previous != _watersysteem_metadata(output_path, signature):
                raise ValueError("Culvert input, settings or output changed")
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
        (
            "hydroobject_primair",
            hydroobject_primair
            if signature is None
            else watersysteem.hydroobject_primair_delen.loc[
                watersysteem.hydroobject_primair_delen.brandgeschikt
            ].copy(),
        ),
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
            if layer_name == "hydroobject_segment":
                features = features.copy()
                features["segment_id"] = range(1, len(features) + 1)
            if layer_name == "hydroobject_verbinding":
                features = _connection_segment_ids(features, temporary_path)
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
        _validate_segment_numbers(temporary_path)
        temporary_path.replace(output_path)
        _write_watersysteem_metadata(
            metadata_path, _watersysteem_metadata(output_path, signature)
        )
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    logger.info(
        "Wrote watersysteem layers %s to %s",
        OUTPUT_LAYERS,
        output_path,
    )
    return output_path
