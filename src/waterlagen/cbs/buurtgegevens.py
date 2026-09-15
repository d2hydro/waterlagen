"""Selected CBS StatLine data for the inwoners- en personenautoanalyse."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import requests
import pandas as pd

from waterlagen import datastore
from waterlagen._geopandas import read_file
from waterlagen.administratieve_gebieden.download import (
    CBS_BUURTCODE_COLUMN,
    CBS_BUURTEN_LAYER,
)
from waterlagen.logger import get_logger

logger = get_logger(__name__)

CBS_KERNCIJFERS_2025_TABLE = "86165NED"
CBS_STATLINE_ODATA_URL = "https://datasets.cbs.nl/odata/v1/CBS/86165NED"
CBS_STATLINE_OBSERVATIONS_URL = f"{CBS_STATLINE_ODATA_URL}/Observations"
CBS_STATLINE_CODES_URL = f"{CBS_STATLINE_ODATA_URL}/WijkenEnBuurtenCodes"
CBS_BUURTGEGEVENS_2025_FILENAME = "buurtgegevens_2025.json"
CBS_REPORT_YEAR = 2025
CBS_PAGE_SIZE = 10_000

CBS_MEASURES = {
    "T001036": "aantal_inwoners",
    "1050010_2": "aantal_huishoudens",
    "A018943_2": "personenautos_totaal",
}
BUURTGEGEVENS_COLUMNS = (
    "buurtcode",
    "aantal_inwoners",
    "aantal_huishoudens",
    "personenautos_totaal",
)

BuurtgegevenValue: TypeAlias = int | float | str | None
BuurtgegevenRow: TypeAlias = dict[str, BuurtgegevenValue]


@dataclass(frozen=True)
class StatLineDownload:
    """Metadata for selected CBS StatLine buurtgegevens."""

    target_path: Path
    source_url: str
    table_identifier: str
    report_year: int
    buurt_count: int
    reused: bool


@dataclass(frozen=True)
class BuurtcodeSystematiek:
    """Comparison of CBS buurtcodes in geometry and StatLine source data."""

    geometry_buurt_count: int
    statline_buurt_count: int
    geometry_codes_without_statline: int


def buurtgegevens_2025_path(download_dir: Path = datastore.cbs_dir) -> Path:
    """Return the datastore path for selected CBS buurtgegevens of 2025."""
    return Path(download_dir) / CBS_BUURTGEGEVENS_2025_FILENAME


def _buurt_filter() -> str:
    measures = " or ".join(f"Measure eq '{measure}'" for measure in CBS_MEASURES)
    return f"({measures}) and startswith(WijkenEnBuurten, 'BU')"


def _request_json(
    url: str,
    *,
    params: dict[str, str | int] | None,
    timeout: int,
) -> dict[str, object]:
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError(
            f"CBS StatLine returned invalid JSON from {response.url}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            f"CBS StatLine returned an unexpected JSON document from {response.url}"
        )
    return payload


def _read_buurtcodes(*, timeout: int) -> list[str]:
    buurtcodes: list[str] = []
    next_url = CBS_STATLINE_CODES_URL
    initial_params: dict[str, str | int] = {
        "$filter": "startswith(Identifier, 'BU')",
        "$select": "Identifier",
        "$orderby": "Identifier",
        "$top": CBS_PAGE_SIZE,
    }
    params: dict[str, str | int] | None = initial_params
    offset = 0

    while next_url:
        payload = _request_json(next_url, params=params, timeout=timeout)
        values = payload.get("value")
        if not isinstance(values, list):
            raise ValueError("CBS StatLine buurtcode response has no value list")
        for value in values:
            if not isinstance(value, dict):
                raise ValueError(
                    "CBS StatLine buurtcode response contains an invalid record"
                )
            buurtcode = value.get("Identifier")
            if not isinstance(buurtcode, str) or not buurtcode.startswith("BU"):
                raise ValueError(
                    "CBS StatLine buurtcode response contains a non-buurt code"
                )
            buurtcodes.append(buurtcode)

        next_link = payload.get("@odata.nextLink")
        if next_link is None:
            next_url = ""
        elif isinstance(next_link, str):
            next_url = next_link
        else:
            raise ValueError("CBS StatLine buurtcode response has an invalid next link")
        if next_url:
            params = None
        elif len(values) == CBS_PAGE_SIZE:
            offset += len(values)
            next_url = CBS_STATLINE_CODES_URL
            params = initial_params | {"$skip": offset}

    if len(buurtcodes) != len(set(buurtcodes)):
        raise ValueError("CBS StatLine returned duplicate buurtcodes")
    return buurtcodes


def _read_selected_observations(*, timeout: int) -> list[dict[str, object]]:
    next_url = CBS_STATLINE_OBSERVATIONS_URL
    initial_params: dict[str, str | int] = {
        "$filter": _buurt_filter(),
        "$select": "Measure,Value,ValueAttribute,WijkenEnBuurten",
        "$orderby": "WijkenEnBuurten,Measure",
        "$top": CBS_PAGE_SIZE,
    }
    params: dict[str, str | int] | None = initial_params
    offset = 0
    observations: list[dict[str, object]] = []

    while next_url:
        payload = _request_json(next_url, params=params, timeout=timeout)
        values = payload.get("value")
        if not isinstance(values, list):
            raise ValueError("CBS StatLine observation response has no value list")
        for value in values:
            if not isinstance(value, dict):
                raise ValueError(
                    "CBS StatLine observation response contains an invalid record"
                )
            observations.append(value)

        next_link = payload.get("@odata.nextLink")
        if next_link is None:
            next_url = ""
        elif isinstance(next_link, str):
            next_url = next_link
        else:
            raise ValueError(
                "CBS StatLine observation response has an invalid next link"
            )
        if next_url:
            params = None
        elif len(values) == CBS_PAGE_SIZE:
            offset += len(values)
            next_url = CBS_STATLINE_OBSERVATIONS_URL
            params = initial_params | {"$skip": offset}

    return observations


def _build_buurtgegevens(
    buurtcodes: list[str], observations: list[dict[str, object]]
) -> tuple[list[BuurtgegevenRow], dict[str, dict[str, str]]]:
    rows: dict[str, BuurtgegevenRow] = {
        buurtcode: {
            "buurtcode": buurtcode,
            "aantal_inwoners": None,
            "aantal_huishoudens": None,
            "personenautos_totaal": None,
        }
        for buurtcode in buurtcodes
    }
    value_attributes: dict[str, dict[str, str]] = {}
    observed_values: set[tuple[str, str]] = set()

    for observation in observations:
        measure = observation.get("Measure")
        buurtcode = observation.get("WijkenEnBuurten")
        if not isinstance(measure, str) or measure not in CBS_MEASURES:
            raise ValueError("CBS StatLine returned an unrequested measure")
        if not isinstance(buurtcode, str) or buurtcode not in rows:
            raise ValueError("CBS StatLine returned a non-buurt code")

        column = CBS_MEASURES[measure]
        if (buurtcode, column) in observed_values:
            raise ValueError(
                f"CBS StatLine returned multiple values for {buurtcode} and {column}"
            )
        observed_values.add((buurtcode, column))
        value = observation.get("Value")
        if value is not None and not isinstance(value, (int, float, str)):
            raise ValueError("CBS StatLine returned a value with an unsupported type")
        rows[buurtcode][column] = value

        value_attribute = observation.get("ValueAttribute")
        if value_attribute not in (None, "None"):
            if not isinstance(value_attribute, str):
                raise ValueError("CBS StatLine returned an invalid value attribute")
            value_attributes.setdefault(buurtcode, {})[column] = value_attribute

    return list(rows.values()), value_attributes


def _write_json_atomically(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".json", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _read_download_count(path: Path) -> int:
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"Existing CBS buurtgegevens file {path} has no rows list")
    return len(rows)


def read_buurtgegevens(
    path: Path,
    *,
    columns: tuple[str, ...],
) -> pd.DataFrame:
    """Read selected columns from downloaded CBS buurtgegevens.

    The source JSON keeps CBS no-data as ``null``. This reader preserves those
    values and verifies that each CBS buurtcode occurs once.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"CBS buurtgegevens {path} do not exist. "
            "Download them with download_buurtgegevens_2025()."
        )
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("CBS buurtgegevens have no rows list")
    data = pd.DataFrame(rows)
    required_columns = (CBS_BUURTCODE_COLUMN, *columns)
    missing_columns = [column for column in required_columns if column not in data]
    if missing_columns:
        names = ", ".join(missing_columns)
        raise ValueError(f"CBS buurtgegevens have no required column(s): {names}")
    if data[CBS_BUURTCODE_COLUMN].isna().any():
        raise ValueError("CBS buurtgegevens contain missing buurtcodes")
    if data[CBS_BUURTCODE_COLUMN].duplicated().any():
        raise ValueError("CBS buurtgegevens contain duplicate buurtcodes")
    return data[list(required_columns)].copy()


def validate_buurtcode_systematiek(
    buurtkaart_path: Path,
    buurtgegevens_path: Path,
) -> BuurtcodeSystematiek:
    """Validate that CBS geometry and StatLine data use one code system.

    This only compares source identifiers. It deliberately does not attach the
    statistics to geometries or otherwise alter either source dataset.

    Parameters
    ----------
    buurtkaart_path : Path
        GeoPackage from :func:`download_wijk_buurtkaart_2025`.
    buurtgegevens_path : Path
        JSON result from :func:`download_buurtgegevens_2025`.

    Raises
    ------
    BuurtcodeSystematiek
        Counts for both sources and geometrical buurtcodes without a StatLine row.

    Raises
    ------
    ValueError
        If either source contains duplicate or non-CBS-buurt codes, or if a
        StatLine code does not occur in the geographical source.
    """
    buurten = read_file(
        buurtkaart_path,
        layer=CBS_BUURTEN_LAYER,
        columns=[CBS_BUURTCODE_COLUMN],
    )
    if CBS_BUURTCODE_COLUMN not in buurten.columns:
        raise ValueError("CBS buurtgeometrie has no buurtcode column")
    geometry_codes = buurten[CBS_BUURTCODE_COLUMN].tolist()
    if not all(
        isinstance(code, str) and code.startswith("BU") for code in geometry_codes
    ):
        raise ValueError("CBS buurtgeometrie contains a non-buurt code")
    if len(geometry_codes) != len(set(geometry_codes)):
        raise ValueError("CBS buurtgeometrie contains duplicate buurtcodes")

    with Path(buurtgegevens_path).open(encoding="utf-8") as file:
        payload = json.load(file)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("CBS StatLine buurtgegevens has no rows list")
    statistic_codes = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("CBS StatLine buurtgegevens contains an invalid row")
        buurtcode = row.get("buurtcode")
        if not isinstance(buurtcode, str) or not buurtcode.startswith("BU"):
            raise ValueError("CBS StatLine buurtgegevens contains a non-buurt code")
        statistic_codes.append(buurtcode)
    if len(statistic_codes) != len(set(statistic_codes)):
        raise ValueError("CBS StatLine buurtgegevens contains duplicate buurtcodes")

    geometry_code_set = set(geometry_codes)
    statistic_code_set = set(statistic_codes)
    if not statistic_code_set.issubset(geometry_code_set):
        raise ValueError(
            "CBS StatLine buurtgegevens contains codes absent from CBS buurtgeometrie"
        )
    return BuurtcodeSystematiek(
        geometry_buurt_count=len(geometry_codes),
        statline_buurt_count=len(statistic_codes),
        geometry_codes_without_statline=len(geometry_code_set - statistic_code_set),
    )


def download_buurtgegevens_2025(
    download_dir: Path = datastore.cbs_dir,
    *,
    target_path: Path | None = None,
    overwrite: bool = True,
    timeout: int = 30,
) -> StatLineDownload:
    """Download only needed 2025 StatLine values for every CBS buurt.

    The CBS OData queries select only neighbourhood codes and the three requested
    measures. The result is JSON so CBS missing values remain ``null`` rather than
    being converted to zero. Non-default CBS value attributes are retained in
    ``metadata.cbs_value_attributes``.

    Parameters
    ----------
    download_dir : Path, optional
        Directory for the selected CBS source data, by default ``datastore.cbs_dir``.
    target_path : Path, optional
        Override for the JSON output path.
    overwrite : bool, optional
        Whether to replace an existing result. When False, the existing result is
        reused without API requests.
    timeout : int, optional
        HTTP timeout in seconds for each CBS request.

    Returns
    -------
    StatLineDownload
        Output path and provenance metadata, including the downloaded buurt count.
    """
    if target_path is None:
        target_path = buurtgegevens_2025_path(download_dir=download_dir)
    else:
        target_path = Path(target_path)

    if target_path.exists() and not overwrite:
        buurt_count = _read_download_count(target_path)
        logger.info("Reusing CBS buurtgegevens 2025 from %s", target_path)
        return StatLineDownload(
            target_path=target_path,
            source_url=CBS_STATLINE_ODATA_URL,
            table_identifier=CBS_KERNCIJFERS_2025_TABLE,
            report_year=CBS_REPORT_YEAR,
            buurt_count=buurt_count,
            reused=True,
        )

    logger.info(
        "Downloading selected CBS StatLine buurtgegevens 2025 to %s", target_path
    )
    buurtcodes = _read_buurtcodes(timeout=timeout)
    observations = _read_selected_observations(timeout=timeout)
    rows, value_attributes = _build_buurtgegevens(buurtcodes, observations)

    if len(rows) != len({row["buurtcode"] for row in rows}):
        raise ValueError("CBS StatLine output has duplicate buurtcodes")

    metadata: dict[str, object] = {
        "source": "CBS StatLine",
        "table_identifier": CBS_KERNCIJFERS_2025_TABLE,
        "report_year": CBS_REPORT_YEAR,
        "odata_root_url": CBS_STATLINE_ODATA_URL,
        "odata_codes_url": CBS_STATLINE_CODES_URL,
        "odata_observations_url": CBS_STATLINE_OBSERVATIONS_URL,
        "odata_observations_filter": _buurt_filter(),
        "columns": list(BUURTGEGEVENS_COLUMNS),
        "buurt_count": len(rows),
        "cbs_value_attributes": value_attributes,
        "missing_value_representation": "null",
    }
    _write_json_atomically(target_path, {"metadata": metadata, "rows": rows})
    logger.info("Downloaded %s CBS buurtgegevens for 2025", len(rows))
    return StatLineDownload(
        target_path=target_path,
        source_url=CBS_STATLINE_ODATA_URL,
        table_identifier=CBS_KERNCIJFERS_2025_TABLE,
        report_year=CBS_REPORT_YEAR,
        buurt_count=len(rows),
        reused=False,
    )
