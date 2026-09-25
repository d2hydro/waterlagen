"""Read land-use codes from the editable, semicolon-separated source table."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from waterlagen.logger import get_logger

logger = get_logger(__name__)
DEFAULT_MAPPING_CSV = Path(__file__).with_name("landgebruik_met_code.csv")


@dataclass(frozen=True)
class LanduseMapping:
    """One grouped source-to-land-use mapping, including both location codes."""

    ids: tuple[str, ...]
    source: str
    layer: str
    field: str
    values: tuple[str, ...]
    description: str
    inside: int
    outside: int


@dataclass(frozen=True)
class LanduseTable:
    """Validated CSV rows shared by classification and the raster legend."""

    path: Path
    rows: tuple[LanduseMapping, ...]

    def by_id(self, mapping_id: str) -> LanduseMapping:
        """Return a stable mapping ID, independent of row order or class code."""
        for row in self.rows:
            if mapping_id in row.ids:
                return row
        raise ValueError(f"Koppeling-ID {mapping_id} ontbreekt in {self.path}")

    def source_values(self, source: str, layer: str) -> dict[str, LanduseMapping]:
        """Index exact source values for one layer; '*' denotes an explicit fallback."""
        result = {}
        for row in self.rows:
            if row.source != source or row.layer != layer:
                continue
            for value in row.values:
                key = value.casefold()
                if key in result:
                    raise ValueError(
                        f"Dubbele bronwaarde {source}/{layer}/{value} in {self.path}"
                    )
                result[key] = row
        if not result:
            raise ValueError(f"Geen koppelingen voor {source}/{layer} in {self.path}")
        return result


def _code(value: str, *, column: str, mapping_id: str) -> int:
    """Require a numeric code; explanations belong in the Toelichting column."""
    text = value.strip()
    if not text.isascii() or not text.isdigit() or not 1 <= int(text) <= 255:
        raise ValueError(
            f"CSV {mapping_id}: {column} moet een geheel getal van 1 t/m 255 zijn: {text!r}"
        )
    return int(text)


def _values(source: str, text: str) -> tuple[str, ...]:
    """Read grouped values; strip the table's explicit description annotations."""
    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    if not lines:
        raise ValueError("Lege Bronwaarde in landgebruik-CSV")
    if lines[0] in {
        "OVERIGE GELDIGE CODES",
        "ALLE OBJECTEN IN LAAG",
        "ALLE WATERDELEN",
    }:
        return ("*",)
    if source == "BRP":
        values = []
        for line in lines:
            match = re.fullmatch(r"(\d+)(?:\s+—\s+.*)?", line)
            if match:
                values.append(match.group(1))
            elif lines != ("343", "Sloot"):
                raise ValueError(f"Ongeldige BRP-bronwaarde: {line!r}")
        if not values:
            raise ValueError(f"Geen gewascodes in BRP-Bronwaarde: {text!r}")
        return tuple(values)
    # These two-line cells contain a source value followed by an explanation.
    if lines == ("grasland agrarisch", "Aanvulling op BRP-gras"):
        return (lines[0],)
    return tuple(line.split(" — ", 1)[0] for line in lines)


def load_landuse_table(path: Path | None = None) -> LanduseTable:
    """Load codes and descriptions without executing prose as classification rules.

    Parameters
    ----------
    path : pathlib.Path, optional
        UTF-8 CSV with semicolon separators. Defaults to the packaged table.

    Returns
    -------
    LanduseTable
        Validated rows. Function selection and building-level rules remain
        Python logic; code columns must contain numbers only.

    Raises
    ------
    ValueError
        Missing columns, duplicate IDs, invalid codes or conflicting legends.
    """
    path = Path(path) if path is not None else DEFAULT_MAPPING_CSV
    required = {
        "Koppeling-ID",
        "Bron",
        "Bronlaag",
        "Bronveld",
        "Bronwaarde",
        "Landgebruik volgens notitie",
        "Binnen",
        "Buiten",
    }
    rows = []
    seen_ids = set()
    descriptions = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV {path} mist kolommen: {', '.join(sorted(missing))}")
        for number, record in enumerate(reader, start=2):
            if None in record or any(record[column] is None for column in required):
                raise ValueError(f"CSV {path}, rij {number}: onjuist aantal kolommen")
            ids = tuple(record["Koppeling-ID"].splitlines())
            if not ids or any(not key.strip() or key in seen_ids for key in ids):
                raise ValueError(
                    f"CSV {path}, rij {number}: leeg of dubbel Koppeling-ID"
                )
            if len(ids) != len(set(ids)):
                raise ValueError(f"CSV {path}, rij {number}: dubbel Koppeling-ID")
            seen_ids.update(ids)
            inside = _code(record["Binnen"], column="Binnen", mapping_id=ids[0])
            outside = _code(record["Buiten"], column="Buiten", mapping_id=ids[0])
            description = record["Landgebruik volgens notitie"].strip()
            if not description:
                raise ValueError(f"CSV {ids[0]}: omschrijving ontbreekt")
            # Several inside classes can deliberately share one outside code,
            # e.g. agricultural grass and nature both become 182 outside dikes.
            if inside in descriptions and descriptions[inside] != description:
                raise ValueError(
                    f"CSV code {inside}: verschillende landgebruiksklassen"
                )
            descriptions[inside] = description
            rows.append(
                LanduseMapping(
                    ids=ids,
                    source=record["Bron"].strip(),
                    layer=record["Bronlaag"].strip().removesuffix(".gml"),
                    field=record["Bronveld"].strip(),
                    values=_values(record["Bron"], record["Bronwaarde"]),
                    description=description,
                    inside=inside,
                    outside=outside,
                )
            )
    if not rows:
        raise ValueError(f"CSV {path} bevat geen koppelingen")
    if {row.inside for row in rows} & {row.outside for row in rows}:
        raise ValueError("CSV gebruikt dezelfde code voor binnen- en buitendijks")
    logger.info("Landgebruikcodes gelezen uit %s (%s groepen)", path, len(rows))
    return LanduseTable(path=path, rows=tuple(rows))
