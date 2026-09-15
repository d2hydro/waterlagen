"""Build the processed inwoners per woon-VBO GeoPackage."""

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

from waterlagen import datastore
from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._geopandas import read_file
from waterlagen._geoparquet import write_geoparquet_atomically
from waterlagen.administratieve_gebieden import CBS_BUURTCODE_COLUMN
from waterlagen.logger import get_logger
from waterlagen.vbo_buurt.build import (
    AANTAL_WOONVBO_COLUMN,
    BAG_VBO_LAYER,
    CBS_BUURT_OUTPUT_LAYER,
    PAND_ID_COLUMN,
    VBO_ID_COLUMN,
)
from waterlagen.vbo_buurt.verdeling import deel_buurtwaarde_per_vbo
from waterlagen.vbo_buurt.hilbert import HILBERT_COLUMN, valideer_hilbert_volgorde

logger = get_logger(__name__)

INWONERS_LAYER = "inwoners"
AANTAL_INWONERS_COLUMN = "aantal_inwoners"
AANTAL_HUISHOUDENS_COLUMN = "aantal_huishoudens"
INWONERS_OBV_HUISHOUDENS_COLUMN = "inwoners_obv_huishoudens"
INWONERS_OBV_WOONVBO_COLUMN = "inwoners_obv_woonvbo"

CBS_VALUE_COLUMNS = (
    AANTAL_INWONERS_COLUMN,
    AANTAL_HUISHOUDENS_COLUMN,
    AANTAL_WOONVBO_COLUMN,
)


@dataclass(frozen=True)
class InwonersBuild:
    """Summary of one inwoners per woon-VBO processing run."""

    target_path: Path
    vbo_count: int
    buurt_count: int
    vbos_with_missing_cbs_data: int
    buurten_without_woonvbo_control: int
    reused: bool
    geoparquet_path: Path | None = None


def _require_columns(data: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in data.columns]
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"Data contain no required column(s): {names}")


def _cbs_values(cbs_buurten: pd.DataFrame) -> pd.DataFrame:
    """Return unique CBS buurtwaarden with missing values kept missing."""
    _require_columns(cbs_buurten, (CBS_BUURTCODE_COLUMN, *CBS_VALUE_COLUMNS))
    values = cbs_buurten[[CBS_BUURTCODE_COLUMN, *CBS_VALUE_COLUMNS]].copy()
    if values[CBS_BUURTCODE_COLUMN].isna().any():
        raise ValueError("CBS buurtgegevens contain missing buurtcodes")
    if values[CBS_BUURTCODE_COLUMN].duplicated().any():
        raise ValueError("CBS buurtgegevens contain duplicate buurtcodes")
    for column in CBS_VALUE_COLUMNS:
        values[column] = pd.to_numeric(values[column], errors="coerce")
    return values


def _control_buurt_sums(
    result: gpd.GeoDataFrame,
    cbs_values: pd.DataFrame,
) -> tuple[int, int]:
    """Validate per-buurt totals and return unavailable-control and missing counts."""
    per_buurt = (
        result.dropna(subset=[CBS_BUURTCODE_COLUMN])
        .groupby(CBS_BUURTCODE_COLUMN, as_index=False)
        .agg(
            actual_count=(VBO_ID_COLUMN, "size"),
            woonvbo_sum=(INWONERS_OBV_WOONVBO_COLUMN, "sum"),
            huishoudens_sum=(INWONERS_OBV_HUISHOUDENS_COLUMN, "sum"),
        )
    )
    controls = cbs_values.merge(
        per_buurt,
        on=CBS_BUURTCODE_COLUMN,
        how="left",
        validate="one_to_one",
    )
    controls["actual_count"] = controls["actual_count"].fillna(0).astype("int64")

    has_woonvbo_control = (
        controls[AANTAL_INWONERS_COLUMN].notna()
        & controls[AANTAL_WOONVBO_COLUMN].notna()
        & controls[AANTAL_WOONVBO_COLUMN].gt(0)
        & np.isclose(controls["actual_count"], controls[AANTAL_WOONVBO_COLUMN])
    )
    has_household_control = (
        has_woonvbo_control
        & controls[AANTAL_HUISHOUDENS_COLUMN].notna()
        & controls[AANTAL_HUISHOUDENS_COLUMN].gt(0)
    )

    invalid_woonvbo_sum = has_woonvbo_control & ~np.isclose(
        controls["woonvbo_sum"],
        controls[AANTAL_INWONERS_COLUMN],
        rtol=1e-9,
        atol=1e-9,
    )
    if invalid_woonvbo_sum.any():
        buurtcode = controls.loc[invalid_woonvbo_sum, CBS_BUURTCODE_COLUMN].iloc[0]
        raise ValueError(
            f"Inwonerbehoudende verdeling for buurt {buurtcode} does not "
            "sum to aantal_inwoners"
        )

    expected_huishoudens_sum = (
        controls[AANTAL_INWONERS_COLUMN]
        * controls[AANTAL_WOONVBO_COLUMN]
        / controls[AANTAL_HUISHOUDENS_COLUMN]
    )
    invalid_huishoudens_sum = has_household_control & ~np.isclose(
        controls["huishoudens_sum"],
        expected_huishoudens_sum,
        rtol=1e-9,
        atol=1e-9,
    )
    if invalid_huishoudens_sum.any():
        buurtcode = controls.loc[invalid_huishoudens_sum, CBS_BUURTCODE_COLUMN].iloc[0]
        raise ValueError(
            f"Huishoudenverdeling for buurt {buurtcode} has an unexpected sum"
        )

    expected_difference = controls[AANTAL_INWONERS_COLUMN] * (
        controls[AANTAL_WOONVBO_COLUMN] / controls[AANTAL_HUISHOUDENS_COLUMN] - 1
    )
    actual_difference = controls["huishoudens_sum"] - controls["woonvbo_sum"]
    unexplained_difference = has_household_control & ~np.isclose(
        actual_difference,
        expected_difference,
        rtol=1e-9,
        atol=1e-9,
    )
    if unexplained_difference.any():
        buurtcode = controls.loc[unexplained_difference, CBS_BUURTCODE_COLUMN].iloc[0]
        raise ValueError(
            f"Difference between inwoners methods for buurt {buurtcode} "
            "is not explained by huishoudens and woon-VBO's"
        )

    buurten_without_woonvbo_control = int((~has_woonvbo_control).sum())
    buurten_without_household_control = int(
        (has_woonvbo_control & ~has_household_control).sum()
    )

    if buurten_without_woonvbo_control:
        logger.warning(
            "Could not perform the inwonerbehoudende controle for %s CBS buurten",
            buurten_without_woonvbo_control,
        )
    if buurten_without_household_control:
        logger.warning(
            "Could not perform the huishoudenscontrole for %s CBS buurten",
            buurten_without_household_control,
        )
    return buurten_without_woonvbo_control, buurten_without_household_control


def bereken_inwoners_per_vbo(
    bag_vbo: gpd.GeoDataFrame,
    cbs_buurten: pd.DataFrame,
) -> tuple[gpd.GeoDataFrame, int, int]:
    """Calculate both inwoners distributions for selected VBO's.

    ``aantal_inwoners`` and ``aantal_huishoudens`` are retained in the result
    so the two calculated variants remain traceable to their CBS source values.
    Missing CBS values and zero denominators produce missing calculated values.

    Returns
    -------
    tuple[geopandas.GeoDataFrame, int, int]
        Result, number of VBO's missing required CBS values, and number of CBS
        buurten for which the inwonerbehoudende control could not be performed.
    """
    _require_columns(bag_vbo, (VBO_ID_COLUMN, CBS_BUURTCODE_COLUMN, HILBERT_COLUMN))
    if bag_vbo.crs is None:
        raise ValueError("BAG VBO data have no CRS")
    if bag_vbo[VBO_ID_COLUMN].isna().any():
        raise ValueError("BAG VBO data contain missing identificaties")
    if bag_vbo[VBO_ID_COLUMN].duplicated().any():
        raise ValueError("BAG VBO data contain duplicate identificaties")
    valideer_hilbert_volgorde(bag_vbo)

    cbs_values = _cbs_values(cbs_buurten)
    bag_columns = [VBO_ID_COLUMN, CBS_BUURTCODE_COLUMN, HILBERT_COLUMN, "geometry"]
    if PAND_ID_COLUMN in bag_vbo.columns:
        bag_columns.insert(1, PAND_ID_COLUMN)
    result = bag_vbo[bag_columns].merge(
        cbs_values,
        on=CBS_BUURTCODE_COLUMN,
        how="left",
        sort=False,
        validate="many_to_one",
    )
    result = gpd.GeoDataFrame(result, geometry="geometry", crs=bag_vbo.crs)
    valideer_hilbert_volgorde(result)
    for column in CBS_VALUE_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result[INWONERS_OBV_HUISHOUDENS_COLUMN] = deel_buurtwaarde_per_vbo(
        result,
        waarde_column=AANTAL_INWONERS_COLUMN,
        noemer_column=AANTAL_HUISHOUDENS_COLUMN,
    )
    result[INWONERS_OBV_WOONVBO_COLUMN] = deel_buurtwaarde_per_vbo(
        result,
        waarde_column=AANTAL_INWONERS_COLUMN,
        noemer_column=AANTAL_WOONVBO_COLUMN,
    )

    missing_cbs_data = result[list(CBS_VALUE_COLUMNS)].isna().any(axis=1)
    missing_count = int(missing_cbs_data.sum())
    if missing_count:
        logger.warning("%s VBO's have missing required CBS values", missing_count)
    zero_denominator = result[AANTAL_HUISHOUDENS_COLUMN].le(0).fillna(False) | result[
        AANTAL_WOONVBO_COLUMN
    ].le(0).fillna(False)
    if zero_denominator.any():
        logger.warning(
            "%s VBO's have a zero CBS denominator; calculated values remain missing",
            int(zero_denominator.sum()),
        )

    buurten_without_woonvbo_control, _ = _control_buurt_sums(result, cbs_values)
    cbs_total = cbs_values[AANTAL_INWONERS_COLUMN].sum(min_count=1)
    logger.info(
        "CBS inwoners totaal: %s; som inwoners_obv_huishoudens: %s; "
        "som inwoners_obv_woonvbo: %s",
        cbs_total,
        result[INWONERS_OBV_HUISHOUDENS_COLUMN].sum(min_count=1),
        result[INWONERS_OBV_WOONVBO_COLUMN].sum(min_count=1),
    )

    output_columns = [VBO_ID_COLUMN]
    if PAND_ID_COLUMN in result.columns:
        output_columns.append(PAND_ID_COLUMN)
    output_columns.extend(
        [
            CBS_BUURTCODE_COLUMN,
            AANTAL_INWONERS_COLUMN,
            AANTAL_HUISHOUDENS_COLUMN,
            AANTAL_WOONVBO_COLUMN,
            INWONERS_OBV_HUISHOUDENS_COLUMN,
            INWONERS_OBV_WOONVBO_COLUMN,
            HILBERT_COLUMN,
            "geometry",
        ]
    )
    return result[output_columns].copy(), missing_count, buurten_without_woonvbo_control


def _read_bag_vbo(path: Path, *, layer: str) -> gpd.GeoDataFrame:
    """Read the selected BAG VBO fields used in the inwoners product."""
    info = pyogrio.read_info(path, layer=layer)
    available_columns = {str(column) for column in info["fields"]}
    required_columns = {VBO_ID_COLUMN, CBS_BUURTCODE_COLUMN, HILBERT_COLUMN}
    missing_columns = required_columns - available_columns
    if missing_columns:
        names = ", ".join(sorted(missing_columns))
        raise ValueError(f"BAG VBO layer {layer} has no required column(s): {names}")
    columns = [VBO_ID_COLUMN, CBS_BUURTCODE_COLUMN, HILBERT_COLUMN]
    if PAND_ID_COLUMN in available_columns:
        columns.append(PAND_ID_COLUMN)
    return read_file(path, layer=layer, columns=columns)


def _read_cbs_buurten(path: Path, *, layer: str) -> pd.DataFrame:
    """Read the CBS values and VBO counts without loading polygon geometries."""
    return read_file(
        path,
        layer=layer,
        columns=[CBS_BUURTCODE_COLUMN, *CBS_VALUE_COLUMNS],
        ignore_geometry=True,
    )


def _read_output_counts(path: Path, *, layer: str) -> tuple[int, int]:
    """Read cached output counts without loading VBO geometries."""
    output = read_file(
        path,
        layer=layer,
        columns=[VBO_ID_COLUMN, CBS_BUURTCODE_COLUMN],
        ignore_geometry=True,
    )
    return len(output), int(output[CBS_BUURTCODE_COLUMN].nunique())


def bouw_inwoners(
    bag_vbo_path: Path = datastore.bag_vbo_path,
    cbs_buurt_path: Path = datastore.cbs_buurt_path,
    *,
    target_path: Path = datastore.inwoners_path,
    geoparquet_path: Path = datastore.inwoners_parquet_path,
    bag_vbo_layer: str = BAG_VBO_LAYER,
    cbs_buurt_layer: str = CBS_BUURT_OUTPUT_LAYER,
    overwrite: bool = True,
    write_geoparquet: bool = False,
) -> InwonersBuild:
    """Build inwoners per woon-VBO from the shared VBO-buurt products.

    The BAG point geometry is retained. CBS values are joined by ``buurtcode``;
    no spatial join is repeated. Optionally write standard GeoParquet in the
    existing Hilbert order. When ``overwrite`` is False, an existing GeoPackage
    is reused without reading the input GeoPackages.
    """
    bag_vbo_path = Path(bag_vbo_path)
    cbs_buurt_path = Path(cbs_buurt_path)
    target_path = Path(target_path)
    geoparquet_path = Path(geoparquet_path)
    if target_path.exists() and not overwrite:
        vbo_count, buurt_count = _read_output_counts(target_path, layer=INWONERS_LAYER)
        logger.info("Reusing inwoners output from %s", target_path)
        written_geoparquet_path = None
        if write_geoparquet:
            started = perf_counter()
            inwoners = read_file(target_path, layer=INWONERS_LAYER)
            valideer_hilbert_volgorde(inwoners)
            written_geoparquet_path = write_geoparquet_atomically(
                inwoners,
                geoparquet_path,
                overwrite=False,
            )
            logger.info("Wrote inwoners GeoParquet in %.1f s", perf_counter() - started)
        return InwonersBuild(
            target_path=target_path,
            vbo_count=vbo_count,
            buurt_count=buurt_count,
            vbos_with_missing_cbs_data=0,
            buurten_without_woonvbo_control=0,
            reused=True,
            geoparquet_path=written_geoparquet_path,
        )
    if not bag_vbo_path.exists():
        raise FileNotFoundError(f"BAG VBO output {bag_vbo_path} does not exist")
    if not cbs_buurt_path.exists():
        raise FileNotFoundError(f"CBS buurt output {cbs_buurt_path} does not exist")

    started = perf_counter()
    bag_vbo = _read_bag_vbo(bag_vbo_path, layer=bag_vbo_layer)
    cbs_buurten = _read_cbs_buurten(cbs_buurt_path, layer=cbs_buurt_layer)
    logger.info("Read inwoners inputs in %.1f s", perf_counter() - started)

    started = perf_counter()
    inwoners, missing_count, unchecked_buurt_count = bereken_inwoners_per_vbo(
        bag_vbo,
        cbs_buurten,
    )
    logger.info("Calculated and validated inwoners in %.1f s", perf_counter() - started)

    started = perf_counter()
    write_geopackage_layer_atomically(
        inwoners,
        target_path,
        layer_name=INWONERS_LAYER,
    )
    logger.info("Wrote inwoners GeoPackage in %.1f s", perf_counter() - started)
    written_geoparquet_path = None
    if write_geoparquet:
        started = perf_counter()
        written_geoparquet_path = write_geoparquet_atomically(
            inwoners,
            geoparquet_path,
            overwrite=overwrite,
        )
        logger.info("Wrote inwoners GeoParquet in %.1f s", perf_counter() - started)
    buurt_count = int(inwoners[CBS_BUURTCODE_COLUMN].nunique())
    logger.info(
        "Completed inwoners output with %s VBO's in %s buurten: %s",
        len(inwoners),
        buurt_count,
        target_path,
    )
    return InwonersBuild(
        target_path=target_path,
        vbo_count=len(inwoners),
        buurt_count=buurt_count,
        vbos_with_missing_cbs_data=missing_count,
        buurten_without_woonvbo_control=unchecked_buurt_count,
        reused=False,
        geoparquet_path=written_geoparquet_path,
    )
