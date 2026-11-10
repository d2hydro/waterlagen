"""Source identifiers retained specifically for culvert inspection."""

import pandas as pd

ID_COLUMNS = (
    "nen3610id",
    "globalid",
    "identificatie",
    "namespace",
    "lokaalID",
    "osm_id",
    "osm_type",
    "code",
    "naam",
    "gml_id",
    "identificatie.namespace",
    "identificatie.lokaalID",
)


def _source_identifiers(row: pd.Series) -> dict[str, str | None]:
    """Preserve ID values with consistent field casing for SQLite."""
    values = {}
    actual = {str(column).casefold(): column for column in row.index}
    for name in ID_COLUMNS:
        value = row.get(actual.get(name.casefold(), name))
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        values[name] = str(value) if pd.notna(value) else None
    return values


def _official_identifier(row: pd.Series) -> tuple[str, str] | None:
    """Return the identifier type and value, including its source namespace."""
    for name in ("nen3610id", "identificatie", "globalid"):
        value = row.get(name)
        if pd.notna(value) and str(value).strip():
            return name, str(value)
    namespace = row.get("namespace")
    if pd.isna(namespace):
        namespace = row.get("identificatie.namespace")
    for name in ("lokaalID", "lokaalid", "identificatie.lokaalID"):
        value = row.get(name)
        if pd.notna(namespace) and pd.notna(value):
            return "namespace/lokaalID", f"{namespace}/{value}"
        if row.get("bron") == "bgt" and pd.notna(value):
            return "bgt/lokaalID", str(value)
    osm_id = row.get("osm_id")
    osm_type = row.get("osm_type")
    if pd.notna(osm_id) and pd.notna(osm_type):
        return "osm", f"{osm_type}/{osm_id}"
    # Our OSM downloader only selects ways; arbitrary user layers need a type.
    if pd.notna(osm_id) and row.get("bronlaag") == "osm_culvert":
        return "osm", f"way/{osm_id}"
    return None
