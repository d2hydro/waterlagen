"""Read land-use codes from the editable, semicolon-separated source table."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from waterlagen.logger import get_logger

logger = get_logger(__name__)
DEFAULT_MAPPING_CSV = Path(__file__).with_name("landgebruik_met_code.csv")

BUILTIN_RULE_IDS = frozenset(
    [f"BAG-{number:03d}" for number in range(1, 35)]
    + [f"NGR-{number:03d}" for number in range(1, 7)]
    + [
        "TOP10NL-BAG-001",
        "TOP10NL-BAG-002",
        "TOP10NL-NGR-BAG-001",
        "TOP10NL-NGR-BAG-002",
    ]
)
HEADER_ALIASES = {
    "Koppel-ID": "Koppeling-ID",
    "LGB-code_binnendijks": "Binnen",
    "LGB-code_buitendijks": "Buiten",
    "LGB_beschrijving": "Landgebruik volgens notitie",
}
MAPPING_FIELDS = {
    ("BRP", "brp_gewas"): "gewascode",
    ("TOP10NL", "top10nl_functioneel_gebied_vlak"): "typefunctioneelgebied",
    ("TOP10NL", "top10nl_functioneel_gebied_multivlak"): "typefunctioneelgebied",
    ("BGT", "bgt_wegdeel"): "bgt-functie",
    ("BGT", "bgt_ondersteunendwegdeel"): "bgt-functie",
    ("BGT", "bgt_begroeidterreindeel"): "bgt-fysiekVoorkomen",
    ("BGT", "bgt_onbegroeidterreindeel"): "",
    ("BGT", "bgt_waterdeel"): "",
}


@dataclass(frozen=True)
class LanduseMapping:
    """A direct mapping or built-in rule; legacy rows can group source values."""

    ids: tuple[str, ...]
    source: str
    layer: str
    field: str
    values: tuple[str, ...]
    description: str
    inside: int
    outside: int
    method: str = "mapping"


@dataclass(frozen=True)
class LanduseTable:
    """Validated CSV rows shared by classification and the raster legend."""

    path: Path
    rows: tuple[LanduseMapping, ...]

    def by_id(self, mapping_id: str) -> LanduseMapping:
        """Return a built-in rule by stable ID, independent of row order or code."""
        for row in self.rows:
            if row.method == "functie" and mapping_id in row.ids:
                return row
        raise ValueError(f"Koppel-ID {mapping_id} ontbreekt in {self.path}")

    def source_values(self, source: str, layer: str) -> dict[str, LanduseMapping]:
        """Index exact source values for one layer; '*' denotes an explicit fallback."""
        result = {}
        for row in self.rows:
            if row.method != "mapping" or row.source != source or row.layer != layer:
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


def _code(value: str, *, column: str, context: str) -> int:
    """Require a numeric code; explanations belong in the Toelichting column."""
    text = value.strip()
    if not text.isascii() or not text.isdigit() or not 1 <= int(text) <= 255:
        raise ValueError(
            f"{context}: {column} moet een geheel getal van 1 t/m 255 zijn: {text!r}"
        )
    return int(text)


def _values(source: str, text: str) -> tuple[str, ...]:
    """Read grouped values; strip the table's explicit description annotations."""
    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    if not lines:
        raise ValueError("Lege Bronwaarde in landgebruik-CSV")
    if lines[0] in {
        "*",
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


def _normalize_record(record: dict[str, str], *, context: str) -> dict[str, str]:
    """Resolve header aliases without silently discarding conflicting values."""
    result = record.copy()
    for name, alias in HEADER_ALIASES.items():
        if (
            name in record
            and alias in record
            and record[name].strip() != record[alias].strip()
        ):
            raise ValueError(f"{context}: conflicterende kolommen {name} en {alias}")
        if name not in result and alias in record:
            result[name] = record[alias]
    return result


def _validate_mapping(row: LanduseMapping, *, context: str) -> None:
    """Only supported source fields can drive a direct mapping."""
    scope = (row.source, row.layer)
    if scope not in MAPPING_FIELDS or row.field != MAPPING_FIELDS[scope]:
        raise ValueError(
            f"{context}: niet ondersteunde combinatie Bron/Bronlaag/Bronveld: "
            f"{row.source}/{row.layer}/{row.field}"
        )
    if not row.field and row.values != ("*",):
        raise ValueError(f"{context}: leeg Bronveld vereist uitsluitend Bronwaarde '*'")
    if row.source == "BRP":
        for value in row.values:
            if value != "*" and (
                not value.isascii() or not value.isdigit() or int(value) <= 0
            ):
                raise ValueError(f"{context}: ongeldige BRP-bronwaarde {value!r}")


def _validate_function(row: LanduseMapping, *, context: str) -> None:
    """Keep BAG identity checks shared with classification of in-memory tables."""
    # Import at call time: bag_landgebruik itself uses LanduseTable.
    from waterlagen.functioneel_landgebruik.bag_landgebruik import FLOOR_MAPPING_IDS

    mapping_id = row.ids[0]
    if not mapping_id.startswith("BAG-"):
        return
    expected = {
        key: function
        for function, floor_mappings in FLOOR_MAPPING_IDS.items()
        for key in floor_mappings.values()
    }
    expected.update(
        {
            "BAG-031": "woonfunctie",
            "BAG-032": "overige gebruiksfunctie",
            "BAG-033": "overige gebruiksfunctie",
        }
    )
    if row.source != "BAG":
        raise ValueError(
            f"{context}: {mapping_id} verwacht bron BAG, maar heeft {row.source!r}"
        )
    if mapping_id in expected and row.values != (expected[mapping_id],):
        raise ValueError(
            f"{context}: {mapping_id} verwacht Bronwaarde {expected[mapping_id]!r}, maar heeft {row.values!r}"
        )


def _read_mapping(
    record: dict[str, str], *, legacy: bool, context: str
) -> LanduseMapping:
    ids = tuple(key.strip() for key in record["Koppel-ID"].splitlines())
    if any(not key for key in ids):
        raise ValueError(f"{context}: leeg Koppel-ID")
    method = record.get("Koppelmethode", "").strip()
    if legacy:
        method = "functie" if any(key in BUILTIN_RULE_IDS for key in ids) else "mapping"
    if method not in {"mapping", "functie"}:
        raise ValueError(f"{context}: onbekende Koppelmethode {method!r}")
    if method == "functie":
        if len(ids) != 1 or ids[0] not in BUILTIN_RULE_IDS:
            raise ValueError(f"{context}: functie vereist één bekend Koppel-ID: {ids}")
    elif any(key in BUILTIN_RULE_IDS for key in ids):
        raise ValueError(
            f"{context}: ingebouwd Koppel-ID vereist Koppelmethode functie"
        )
    if not legacy and len(ids) > 1:
        raise ValueError(f"{context}: maximaal één Koppel-ID per rij")

    source = record["Bron"].strip()
    layer = record["Bronlaag"].strip().removesuffix(".gml")
    field = record["Bronveld"].strip()
    text = record["Bronwaarde"].strip()
    if legacy:
        values = _values(source, text)
        if (
            source == "BGT"
            and layer in {"bgt_waterdeel", "bgt_onbegroeidterreindeel"}
            and values == ("*",)
        ):
            field = ""
    else:
        if not text or len(text.splitlines()) != 1:
            raise ValueError(f"{context}: precies één Bronwaarde per rij vereist")
        values = (text,)
    if source == "BRP" and method == "mapping":
        # Numeric source codes are normalized identically for duplicate detection.
        values = tuple(
            str(int(value)) if value.isascii() and value.isdigit() else value
            for value in values
        )
    description = record["LGB_beschrijving"].strip()
    if not description:
        raise ValueError(f"{context}: LGB_beschrijving ontbreekt")
    row = LanduseMapping(
        ids=ids,
        source=source,
        layer=layer,
        field=field,
        values=values,
        description=description,
        inside=_code(
            record["LGB-code_binnendijks"],
            column="LGB-code_binnendijks (Binnen)",
            context=context,
        ),
        outside=_code(
            record["LGB-code_buitendijks"],
            column="LGB-code_buitendijks (Buiten)",
            context=context,
        ),
        method=method,
    )
    if method == "mapping":
        _validate_mapping(row, context=context)
    else:
        _validate_function(row, context=context)
    return row


def load_landuse_table(path: Path | None = None) -> LanduseTable:
    """Load codes and descriptions without executing prose as classification rules.

    Parameters
    ----------
    path : pathlib.Path, optional
        UTF-8 CSV with semicolon separators (an optional BOM is accepted).
        Defaults to the packaged table. New tables use ``Koppelmethode`` and
        one source value per row. Legacy headers and grouped values remain
        supported when ``Koppelmethode`` is absent.

    Returns
    -------
    LanduseTable
        Validated rows. Function selection and building-level rules remain
        Python logic; code columns must contain numbers only.

    Raises
    ------
    ValueError
        Invalid headers, methods, IDs, source mappings, codes or descriptions.
    """
    path = Path(path) if path is not None else DEFAULT_MAPPING_CSV
    required = {
        "Koppel-ID",
        "Bron",
        "Bronlaag",
        "Bronveld",
        "Bronwaarde",
        "LGB_beschrijving",
        "LGB-code_binnendijks",
        "LGB-code_buitendijks",
    }
    rows = []
    seen_ids = set()
    descriptions = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            raise ValueError(f"CSV {path}: dubbele kolomnamen")
        available = set(headers)
        available.update(
            name for name, alias in HEADER_ALIASES.items() if alias in headers
        )
        missing = required.difference(available)
        if missing:
            raise ValueError(
                f"CSV {path} mist kolommen: {', '.join(sorted(missing))}; gebruik UTF-8 en puntkomma's"
            )
        legacy = "Koppelmethode" not in headers
        for number, record in enumerate(reader, start=2):
            if None in record or any(value is None for value in record.values()):
                raise ValueError(f"CSV {path}, rij {number}: onjuist aantal kolommen")
            context = f"CSV {path}, rij {number}"
            record = _normalize_record(record, context=context)
            row = _read_mapping(record, legacy=legacy, context=context)
            if len(row.ids) != len(set(row.ids)) or seen_ids.intersection(row.ids):
                raise ValueError(f"{context}: dubbel Koppel-ID (Koppeling-ID)")
            seen_ids.update(row.ids)
            # Several inside classes can deliberately share one outside code,
            # e.g. agricultural grass and nature both become 182 outside dikes.
            if (
                row.inside in descriptions
                and descriptions[row.inside] != row.description
            ):
                raise ValueError(
                    f"CSV code {row.inside}: verschillende landgebruiksklassen"
                )
            descriptions[row.inside] = row.description
            rows.append(row)
    if not rows:
        raise ValueError(f"CSV {path} bevat geen koppelingen")
    if {row.inside for row in rows} & {row.outside for row in rows}:
        raise ValueError("CSV gebruikt dezelfde code voor binnen- en buitendijks")
    table = LanduseTable(path=path, rows=tuple(rows))
    for source, layer in sorted(
        {(row.source, row.layer) for row in rows if row.method == "mapping"}
    ):
        table.source_values(source, layer)
    logger.info("Landgebruikcodes gelezen uit %s (%s rijen)", path, len(rows))
    return table
