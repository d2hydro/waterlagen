"""Culvert crossings and persistent human assessments of drainage boundaries."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from osgeo import ogr
from shapely import get_parts, line_merge, normalize, union_all
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

from waterlagen._crs import same_crs
from waterlagen._downloads import _temporary_path, validate_geopackage
from waterlagen._geopackage import write_geopackage_layer
from waterlagen._geopandas import read_file
from waterlagen._production import _file_identity
from waterlagen.logger import get_logger
from waterlagen.settings import settings

from ._duiker_identiteit import ID_COLUMNS, _official_identifier
from ._duiker_inbranding import _read_burn_counts
from .brandlagen import _digest

logger = get_logger(__name__)
LINE_LAYER = "duikers_afwateringsgrens"
POLYGON_LAYER = "duikervlakken_afwateringsgrens"
ARCHIVE_TABLE = "beoordelingsarchief"
LEGACY_LAYERS = (
    "duiker_grenskruisingen",
    "duiker_grensdoorsnijdingen",
    "beoordelingsarchief_lijnen",
    "beoordelingsarchief_vlakken",
)
REVIEW_DEFAULTS = {
    "bestaan": "",
    "ligging": "",
    "opmerking": "",
    "beoordelaar": "",
    "datum_beoordeling": "",
}
REVIEW_COLUMNS = [
    "id",
    "code",
    *REVIEW_DEFAULTS,
    "ingebrand",
    "reden_niet_ingebrand",
    "duiker_key",
    "geometry",
]
SIGNAL_COLUMNS = [
    "id",
    "code",
    *REVIEW_DEFAULTS,
    "ingebrand",
    "reden_niet_ingebrand",
    "duiker_key",
    "geometrie_key",
    "sleuteltype",
    "id_type",
    "bron",
    "bron_id",
    "bronbestand",
    "bronlaag",
    "bron_fid",
    "bronversie",
    *(name for name in ID_COLUMNS if name != "code"),
    "behandeling",
    "reden",
    "aantal_kruisingen",
    "segment_keys",
    "geometry",
]


def _frame(records: list[dict], columns: list[str]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        records, columns=columns, geometry="geometry", crs=settings.crs
    )


def _parts(geometry: BaseGeometry, kind: str) -> list[BaseGeometry]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == kind:
        return [geometry]
    result = []
    if hasattr(geometry, "geoms"):
        for part in get_parts(geometry):
            result.extend(_parts(part, kind))
    return result


def _line_crossings(line: LineString, areas: gpd.GeoDataFrame) -> list[dict]:
    """Classify open intervals; touching and boundary-following yield no transition."""
    boundary = union_all(areas.geometry.boundary)
    intervals = []
    # Work per original edge, so a self-crossing line has unambiguous positions.
    for start, end in zip(line.coords[:-1], line.coords[1:]):
        edge = LineString([start, end])
        if edge.length == 0:
            continue
        contacts = edge.intersection(boundary)
        cuts = {0.0, edge.length}
        for point in _parts(contacts, "Point"):
            cuts.add(edge.project(point))
        for overlap in _parts(contacts, "LineString"):
            cuts.update(
                edge.project(Point(coord))
                for coord in (overlap.coords[0], overlap.coords[-1])
            )
        distances = sorted(cuts)
        for left, right in pairwise(distances):
            middle = edge.interpolate((left + right) / 2)
            inside = areas.loc[areas.contains(middle), "segment_key"]
            key = str(inside.iloc[0]) if len(inside) == 1 else None
            intervals.append((key, edge.interpolate(left)))
    crossings = []
    for (previous, _), (current, point) in pairwise(intervals):
        if previous is not None and current is not None and previous != current:
            crossings.append(
                {"segment_a": previous, "segment_b": current, "geometry": point}
            )
    return crossings


def _crossings(geometry: BaseGeometry, areas: gpd.GeoDataFrame) -> list[dict]:
    if geometry.geom_type in {"LineString", "MultiLineString"}:
        merged = line_merge(geometry)
        return [
            crossing
            for line in _parts(merged, "LineString")
            for crossing in _line_crossings(line, areas)
        ]
    crossings = []
    candidates = areas.loc[areas.intersection(geometry).area > 0]
    for position, first in enumerate(candidates.itertuples()):
        for second in candidates.iloc[position + 1 :].itertuples():
            shared = first.geometry.boundary.intersection(second.geometry.boundary)
            interior = shared.intersection(geometry).difference(geometry.boundary)
            for part in _parts(interior, "LineString"):
                if part.length > 0:
                    crossings.append(
                        {
                            "segment_a": str(first.segment_key),
                            "segment_b": str(second.segment_key),
                            "geometry": part,
                        }
                    )
    return crossings


def _read_culverts(run_dir: Path) -> gpd.GeoDataFrame:
    """Use all selected registrations; enrich legacy controls from the overview."""
    controls = read_file(run_dir / "controle.gpkg", layer="duikers_waternet")
    overview = run_dir / "brandlagen.gpkg"
    if overview.exists():
        columns = [*ID_COLUMNS, "bronversie"]
        lookup = {}
        for layer, _ in pyogrio.list_layers(overview):
            features = read_file(overview, layer=layer)
            if layer != "hydamo_duikers":
                if "rol" not in features:
                    continue
                features = features.loc[features.rol.eq("duiker")]
            for _, row in features.iterrows():
                key = (row.bronbestand, row.bronlaag, int(row.bron_fid))
                lookup[key] = row
        for index, row in controls.iterrows():
            original = lookup.get((row.bronbestand, row.bronlaag, int(row.bron_fid)))
            if original is None:
                continue
            for column in columns:
                if pd.notna(original.get(column)):
                    controls.loc[index, column] = str(original[column])
    fallback = _digest(
        _file_identity(overview if overview.exists() else run_dir / "controle.gpkg")
    )
    if "bronversie" not in controls:
        controls["bronversie"] = fallback
    controls["bronversie"] = controls.bronversie.fillna(fallback)
    return controls


def _identity(row: pd.Series) -> dict[str, str]:
    official = _official_identifier(row)
    if official is not None:
        id_type, identifier = official
        key = _digest([row.bron, id_type, identifier])
        kind = "officiele_id"
    else:
        id_type, identifier = "", ""
        key = _digest(
            [row.bron, row.bronversie, row.bronbestand, row.bronlaag, int(row.bron_fid)]
        )
        kind = "bronversie"
    return {
        "duiker_key": key,
        "sleuteltype": kind,
        "id": identifier,
        "id_type": id_type,
        "geometrie_key": _digest(normalize(row.geometry).wkb_hex),
    }


def _burn_status(row: pd.Series, counts: dict, complete: bool) -> tuple[str, str]:
    evidence = counts.get(row.bron_id)
    if evidence is not None and evidence["toegepast"] > 0:
        return "ja", ""
    if row.behandeling != "aanvoer":
        reasons = {
            "dubbel": "dubbele registratie; voorkeursbron gebruikt",
            "primair_primair": "uitsluitend primaire aansluitingen",
        }
        return "nee", reasons.get(row.behandeling, str(row.reden))
    if evidence is None or not complete:
        return (
            "onbekend",
            "geen volledige, geldige registratie van daadwerkelijke inbranding",
        )
    if evidence["winnend"] == 0:
        return (
            "nee",
            "geen winnende duikercellen: verdrongen of uitgesloten bij rasterisatie",
        )
    if evidence["geldige_dem"] == 0:
        return "nee", "geen geldige DEM-cellen op het winnende traject"
    return "nee", "geen hoogtewijziging in opgeslagen DEM (nulwaarde of afronding)"


def _has_review(row: pd.Series) -> bool:
    for column, default in REVIEW_DEFAULTS.items():
        value = row.get(column)
        if pd.notna(value) and str(value) not in {"", default, "niet_beoordeeld"}:
            return True
    return False


def _preserve_reviews(
    current: gpd.GeoDataFrame, previous: Path | None
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    archive_columns = [*SIGNAL_COLUMNS, "archiefreden", "gearchiveerd_op"]
    archive = []
    if previous is None or not previous.exists():
        return current, _frame(archive, archive_columns)
    available = set(pyogrio.list_layers(previous)[:, 0])
    review_layers = [name for name in (LINE_LAYER, POLYGON_LAYER) if name in available]
    if not review_layers:
        raise ValueError("Bestaande signaalkaart mist de verwachte beoordelingslagen")
    if ARCHIVE_TABLE in available:
        archived = pyogrio.read_dataframe(previous, layer=ARCHIVE_TABLE)
        if any(
            not same_crs(crs, settings.crs) for crs in archived.geometrie_crs.unique()
        ):
            raise ValueError("Beoordelingsarchief heeft een afwijkend CRS")
        geometry = gpd.GeoSeries.from_wkb(
            archived.pop("geometrie_wkb").map(bytes.fromhex), crs=settings.crs
        )
        archived = gpd.GeoDataFrame(archived, geometry=geometry, crs=settings.crs)
        archive.extend(archived.to_dict("records"))
    for layer in ("beoordelingsarchief_lijnen", "beoordelingsarchief_vlakken"):
        if layer in available:
            archive.extend(read_file(previous, layer=layer).to_dict("records"))
    old = pd.concat(
        [read_file(previous, layer=name) for name in review_layers],
        ignore_index=True,
    )
    if old.duiker_key.duplicated().any():
        raise ValueError("Beoordelingen bevatten dubbele duikeridentiteiten")
    positions = {key: index for index, key in current.duiker_key.items()}
    for _, row in old.iterrows():
        index = positions.get(row.duiker_key)
        previous_geometry = _digest(normalize(row.geometry).wkb_hex)
        if (
            index is not None
            and current.loc[index, "geometrie_key"] == previous_geometry
        ):
            for column in REVIEW_DEFAULTS:
                value = row.get(column)
                current.loc[index, column] = (
                    "" if pd.isna(value) or value == "niet_beoordeeld" else value
                )
        elif _has_review(row):
            record = row.to_dict()
            record["archiefreden"] = (
                "geometrie gewijzigd"
                if index is not None
                else "signaal verdwenen of bronidentiteit gewijzigd"
            )
            record["gearchiveerd_op"] = datetime.now(UTC).isoformat()
            archive.append(record)
    for record in archive:
        if "id" not in record:
            record["id"] = record.get("officiele_id", record.get("nen3610id", ""))
    return current, _frame(archive, archive_columns)


def _write_archive(archive: gpd.GeoDataFrame, path: Path) -> None:
    """Keep past assessments and exact geometries in one non-spatial table."""
    columns = [name for name in REVIEW_COLUMNS if name != "geometry"]
    records = pd.DataFrame(archive[[*columns, "archiefreden", "gearchiveerd_op"]])
    records["geometrie_wkb"] = pd.Series(
        [geometry.wkb_hex for geometry in archive.geometry],
        index=archive.index,
        dtype=object,
    )
    records["geometrie_crs"] = archive.crs.to_string()
    pyogrio.write_dataframe(records, path, layer=ARCHIVE_TABLE, driver="GPKG")
    written = pyogrio.read_dataframe(path, layer=ARCHIVE_TABLE)
    if len(written) != len(records):
        raise ValueError("Beoordelingsarchief is niet volledig opgeslagen")


def _remove_legacy_layers(path: Path, omitted: tuple[str, ...] = ()) -> None:
    """Remove superseded map layers only after their assessments were preserved."""
    dataset = ogr.Open(str(path), update=1)
    try:
        for name in (*LEGACY_LAYERS, *omitted):
            if (
                dataset.GetLayerByName(name) is not None
                and dataset.DeleteLayer(name) != 0
            ):
                raise ValueError(
                    f"Oude signaalkaartlaag kon niet worden verwijderd: {name}"
                )
    finally:
        dataset = None


def write_duiker_signaalkaart(
    run_dir: Path,
    *,
    output_path: Path | None = None,
    beoordelingen_path: Path | None = None,
) -> Path:
    """Write culverts crossing final drainage boundaries, retaining assessments.

    Parameters
    ----------
    run_dir : pathlib.Path
        Existing production directory with final areas, selected culvert controls
        and, when available, burn-input overview and per-tile burn evidence.
    output_path : pathlib.Path, optional
        Defaults to ``run_dir/signaalkaart.gpkg``. Regenerates this derived file
        atomically. Empty polygon layers and archives are omitted. If there are no
        signals, an empty line layer is retained. Other production files are unchanged.
    beoordelingen_path : pathlib.Path, optional
        Previous signal map, for example from another run. Defaults to the existing
        output. Assessments transfer only for matching source identity and geometry;
        changed or disappeared assessed objects are archived. Source-version keys
        are used conservatively when no official identifier is available.

    Returns
    -------
    pathlib.Path
        Signal GeoPackage, with separate line and original polygon layers,
        and one non-spatial assessment archive. Previous spatial archives are
        migrated to this table, retaining their exact geometry as WKB hex and CRS.

    Raises
    ------
    ValueError
        Missing or incompatible CRS, invalid geometries, ambiguous source IDs,
        incompatible assessments or concurrent changes to the assessment file.

    Notes
    -----
    No downloads or terrain calculations are performed. Mere boundary touches,
    boundary-following lines and transitions to uncovered areas are excluded.
    ``ingebrand=ja`` means at least one stored DEM cell changed due to this culvert
    on a calculation grid; it does not imply a fully burned trajectory. Missing
    evidence yields ``onbekend`` unless a preparation exclusion establishes no burn.
    """
    run_dir = Path(run_dir)
    target = Path(output_path or run_dir / "signaalkaart.gpkg")
    previous = Path(beoordelingen_path) if beoordelingen_path is not None else target
    if target.exists() and previous.resolve() != target.resolve():
        raise ValueError(
            "Gebruik een nieuw uitvoerpad bij overname uit een andere signaalkaart"
        )
    previous_identity = [
        _file_identity(previous),
        _file_identity(Path(str(previous) + "-wal")),
    ]
    areas = read_file(
        run_dir / "afwateringseenheden.gpkg", layer="afvoergebiedaanvoergebied"
    )
    culverts = _read_culverts(run_dir)
    for name, features in (("afwateringseenheden", areas), ("duikers", culverts)):
        if features.crs is None or not same_crs(features.crs, settings.crs):
            raise ValueError(f"Signaalkaart: afwijkend of ontbrekend CRS voor {name}")
        if (
            features.geometry.isna().any()
            or (~features.is_valid).any()
            or features.is_empty.any()
        ):
            raise ValueError(f"Signaalkaart: ongeldige of lege geometrie in {name}")
    if areas.segment_key.isna().any():
        raise ValueError("Afwateringseenheden zonder segment_key")
    areas = areas[["segment_key", "geometry"]].dissolve(
        by="segment_key", as_index=False
    )
    counts, complete = _read_burn_counts(
        sorted((run_dir / "berekening" / "tegels").glob("*/dem_2m.tif"))
    )
    records = []
    identities = [_identity(row) for _, row in culverts.iterrows()]
    duplicated = pd.Series(
        [identity["duiker_key"] for identity in identities], dtype=str
    ).duplicated(keep=False)
    logger.info(
        "Controleren van %s geselecteerde duikers op afwateringsgrenzen", len(culverts)
    )
    for number, ((_, row), identity, duplicate) in enumerate(
        zip(culverts.iterrows(), identities, duplicated), start=1
    ):
        if number % 1000 == 0:
            logger.info(
                "Afwateringsgrenzen gecontroleerd voor %s/%s duikers",
                number,
                len(culverts),
            )
        if duplicate:
            # Multiple source registrations can describe one official object.
            # Keep them all, but do not transfer reviews across source versions.
            identity["duiker_key"] = _digest(
                [
                    identity["duiker_key"],
                    row.bronversie,
                    row.bronbestand,
                    row.bronlaag,
                    int(row.bron_fid),
                ]
            )
            identity["sleuteltype"] = "bronversie"
        indices = areas.sindex.query(row.geometry, predicate="intersects")
        nearby = areas.iloc[indices]
        crossings = _crossings(row.geometry, nearby)
        if not crossings:
            continue
        record = row.to_dict()
        record.update(identity)
        record.update(REVIEW_DEFAULTS)
        record["ingebrand"], record["reden_niet_ingebrand"] = _burn_status(
            row, counts, complete
        )
        record["aantal_kruisingen"] = len(crossings)
        record["segment_keys"] = json.dumps(
            sorted(
                {item[key] for item in crossings for key in ("segment_a", "segment_b")}
            )
        )
        records.append(record)
    signals = _frame(records, SIGNAL_COLUMNS)
    if signals.duiker_key.duplicated().any():
        raise ValueError(
            "Dubbele officiële duiker-ID in signaalkaart; maak de bronregistraties eenduidig"
        )
    signals, archive = _preserve_reviews(signals, previous)
    polygons = signals.geom_type.isin(["Polygon", "MultiPolygon"])
    layers = {
        LINE_LAYER: signals.loc[~polygons, REVIEW_COLUMNS],
        POLYGON_LAYER: signals.loc[polygons, REVIEW_COLUMNS],
    }
    omitted = tuple(
        name
        for name, features in layers.items()
        if features.empty and (name == POLYGON_LAYER or not signals.empty)
    )
    layers = {
        name: features for name, features in layers.items() if name not in omitted
    }
    if archive.empty:
        omitted = (*omitted, ARCHIVE_TABLE)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(target, suffix=".gpkg")
    temporary.unlink(missing_ok=True)
    try:
        if target.exists():
            with (
                closing(sqlite3.connect(target)) as source,
                closing(sqlite3.connect(temporary)) as destination,
            ):
                source.backup(destination)
        for name, features in layers.items():
            write_geopackage_layer(features, temporary, layer_name=name, mode="w")
        if not archive.empty:
            _write_archive(archive, temporary)
        _remove_legacy_layers(temporary, omitted)
        validate_geopackage(temporary)
        for name, features in layers.items():
            written = read_file(temporary, layer=name)
            if len(written) != len(features) or not same_crs(written.crs, settings.crs):
                raise ValueError(f"Signaalkaartvalidatie mislukt voor {name}")
        if previous_identity != [
            _file_identity(previous),
            _file_identity(Path(str(previous) + "-wal")),
        ]:
            raise ValueError(
                "Beoordelingen zijn tijdens het schrijven gewijzigd; probeer opnieuw"
            )
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    logger.info("Signaalkaart geschreven: %s (%s duikers)", target, len(signals))
    return target
