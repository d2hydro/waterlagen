"""Build the processed personenauto's per woon-VBO GeoPackage."""

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
from waterlagen.cbs import buurtgegevens_2025_path, read_buurtgegevens
from waterlagen.logger import get_logger
from waterlagen.vbo_buurt import deel_buurtwaarde_per_vbo
from waterlagen.vbo_buurt.build import (
    AANTAL_WOONVBO_COLUMN,
    BAG_VBO_LAYER,
    CBS_BUURT_OUTPUT_LAYER,
    PAND_ID_COLUMN,
    VBO_ID_COLUMN,
)
from waterlagen.vbo_buurt.hilbert import HILBERT_COLUMN, valideer_hilbert_volgorde

logger = get_logger(__name__)

AUTOS_LAYER = "autos"
PERSONENAUTOS_TOTAAL_COLUMN = "personenautos_totaal"
PERSONENAUTOS_COLUMN = "personenautos"


@dataclass(frozen=True)
class AutosBuild:
    """Summary of one personenauto's per woon-VBO processing run."""

    target_path: Path
    vbo_count: int
    buurt_count: int
    vbos_with_missing_cbs_data: int
    buurten_without_control: int
    reused: bool
    geoparquet_path: Path | None = None


def _require_columns(data: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in data.columns]
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"Data contain no required column(s): {names}")


def _cbs_autos_values(cbs_buurten: pd.DataFrame) -> pd.DataFrame:
    """Return unique CBS auto totals and woon-VBO counts per buurt."""
    _require_columns(
        cbs_buurten,
        (
            CBS_BUURTCODE_COLUMN,
            AANTAL_WOONVBO_COLUMN,
            PERSONENAUTOS_TOTAAL_COLUMN,
        ),
    )
    values = cbs_buurten[
        [
            CBS_BUURTCODE_COLUMN,
            AANTAL_WOONVBO_COLUMN,
            PERSONENAUTOS_TOTAAL_COLUMN,
        ]
    ].copy()
    if values[CBS_BUURTCODE_COLUMN].isna().any():
        raise ValueError("CBS buurtgegevens contain missing buurtcodes")
    if values[CBS_BUURTCODE_COLUMN].duplicated().any():
        raise ValueError("CBS buurtgegevens contain duplicate buurtcodes")
    values[AANTAL_WOONVBO_COLUMN] = pd.to_numeric(
        values[AANTAL_WOONVBO_COLUMN], errors="coerce"
    )
    values[PERSONENAUTOS_TOTAAL_COLUMN] = pd.to_numeric(
        values[PERSONENAUTOS_TOTAAL_COLUMN], errors="coerce"
    )
    return values


def _control_buurt_sums(
    result: gpd.GeoDataFrame,
    cbs_values: pd.DataFrame,
) -> int:
    """Validate vectorized per-buurt personenauto totals."""
    per_buurt = (
        result.dropna(subset=[CBS_BUURTCODE_COLUMN])
        .groupby(CBS_BUURTCODE_COLUMN, as_index=False)
        .agg(
            actual_count=(VBO_ID_COLUMN, "size"),
            personenautos_sum=(PERSONENAUTOS_COLUMN, "sum"),
        )
    )
    controls = cbs_values.merge(
        per_buurt,
        on=CBS_BUURTCODE_COLUMN,
        how="left",
        validate="one_to_one",
    )
    controls["actual_count"] = controls["actual_count"].fillna(0).astype("int64")
    has_control = (
        controls[PERSONENAUTOS_TOTAAL_COLUMN].notna()
        & controls[AANTAL_WOONVBO_COLUMN].notna()
        & controls[AANTAL_WOONVBO_COLUMN].gt(0)
        & np.isclose(controls["actual_count"], controls[AANTAL_WOONVBO_COLUMN])
    )
    invalid_sum = has_control & ~np.isclose(
        controls["personenautos_sum"],
        controls[PERSONENAUTOS_TOTAAL_COLUMN],
        rtol=1e-9,
        atol=1e-9,
    )
    if invalid_sum.any():
        buurtcode = controls.loc[invalid_sum, CBS_BUURTCODE_COLUMN].iloc[0]
        raise ValueError(
            f"Personenautoverdeling for buurt {buurtcode} does not sum to "
            "personenautos_totaal"
        )

    buurten_without_control = int((~has_control).sum())
    if buurten_without_control:
        logger.warning(
            "Could not perform the personenautocontrole for %s CBS buurten",
            buurten_without_control,
        )
    return buurten_without_control


def bereken_personenautos_per_vbo(
    bag_vbo: gpd.GeoDataFrame,
    cbs_buurten: pd.DataFrame,
) -> tuple[gpd.GeoDataFrame, int, int]:
    """Distribute CBS personenauto totals vectorized over woon-VBO's.

    The source total is retained for traceability. Missing source values and
    zero woon-VBO denominators result in missing ``personenautos`` values.
    """
    _require_columns(bag_vbo, (VBO_ID_COLUMN, CBS_BUURTCODE_COLUMN, HILBERT_COLUMN))
    if bag_vbo.crs is None:
        raise ValueError("BAG VBO data have no CRS")
    if bag_vbo[VBO_ID_COLUMN].isna().any():
        raise ValueError("BAG VBO data contain missing identificaties")
    if bag_vbo[VBO_ID_COLUMN].duplicated().any():
        raise ValueError("BAG VBO data contain duplicate identificaties")
    valideer_hilbert_volgorde(bag_vbo)

    cbs_values = _cbs_autos_values(cbs_buurten)
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
    result[PERSONENAUTOS_COLUMN] = deel_buurtwaarde_per_vbo(
        result,
        waarde_column=PERSONENAUTOS_TOTAAL_COLUMN,
        noemer_column=AANTAL_WOONVBO_COLUMN,
    )

    missing_cbs_data = (
        result[[AANTAL_WOONVBO_COLUMN, PERSONENAUTOS_TOTAAL_COLUMN]].isna().any(axis=1)
    )
    missing_count = int(missing_cbs_data.sum())
    if missing_count:
        logger.warning("%s VBO's have missing required CBS values", missing_count)
    zero_woonvbo = result[AANTAL_WOONVBO_COLUMN].le(0).fillna(False)
    if zero_woonvbo.any():
        logger.warning(
            "%s VBO's have aantal_woonvbo equal to zero; personenautos remain missing",
            int(zero_woonvbo.sum()),
        )

    buurten_without_control = _control_buurt_sums(result, cbs_values)
    logger.info(
        "CBS personenautos totaal: %s; som personenautos: %s",
        cbs_values[PERSONENAUTOS_TOTAAL_COLUMN].sum(min_count=1),
        result[PERSONENAUTOS_COLUMN].sum(min_count=1),
    )

    output_columns = [VBO_ID_COLUMN]
    if PAND_ID_COLUMN in result.columns:
        output_columns.append(PAND_ID_COLUMN)
    output_columns.extend(
        [
            CBS_BUURTCODE_COLUMN,
            PERSONENAUTOS_TOTAAL_COLUMN,
            AANTAL_WOONVBO_COLUMN,
            PERSONENAUTOS_COLUMN,
            HILBERT_COLUMN,
            "geometry",
        ]
    )
    return result[output_columns].copy(), missing_count, buurten_without_control


def _read_bag_vbo(path: Path, *, layer: str) -> gpd.GeoDataFrame:
    """Read selected BAG VBO fields while retaining their point geometry."""
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


def _read_cbs_autos(
    cbs_buurt_path: Path,
    cbs_buurtgegevens_path: Path,
    *,
    layer: str,
) -> pd.DataFrame:
    """Combine existing woon-VBO counts and source CBS personenauto totals."""
    woonvbo_counts = read_file(
        cbs_buurt_path,
        layer=layer,
        columns=[CBS_BUURTCODE_COLUMN, AANTAL_WOONVBO_COLUMN],
        ignore_geometry=True,
    )
    personenautos = read_buurtgegevens(
        cbs_buurtgegevens_path,
        columns=(PERSONENAUTOS_TOTAAL_COLUMN,),
    )
    return woonvbo_counts.merge(
        personenautos,
        on=CBS_BUURTCODE_COLUMN,
        how="left",
        validate="one_to_one",
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


def bouw_autos(
    bag_vbo_path: Path = datastore.bag_vbo_path,
    cbs_buurt_path: Path = datastore.cbs_buurt_path,
    cbs_buurtgegevens_path: Path = buurtgegevens_2025_path(),
    *,
    target_path: Path = datastore.autos_path,
    geoparquet_path: Path = datastore.autos_parquet_path,
    bag_vbo_layer: str = BAG_VBO_LAYER,
    cbs_buurt_layer: str = CBS_BUURT_OUTPUT_LAYER,
    overwrite: bool = True,
    write_geoparquet: bool = False,
) -> AutosBuild:
    """Build personenauto's per woon-VBO without a new spatial join."""
    bag_vbo_path = Path(bag_vbo_path)
    cbs_buurt_path = Path(cbs_buurt_path)
    cbs_buurtgegevens_path = Path(cbs_buurtgegevens_path)
    target_path = Path(target_path)
    geoparquet_path = Path(geoparquet_path)
    if target_path.exists() and not overwrite:
        vbo_count, buurt_count = _read_output_counts(target_path, layer=AUTOS_LAYER)
        logger.info("Reusing autos output from %s", target_path)
        written_geoparquet_path = None
        if write_geoparquet:
            started = perf_counter()
            autos = read_file(target_path, layer=AUTOS_LAYER)
            valideer_hilbert_volgorde(autos)
            written_geoparquet_path = write_geoparquet_atomically(
                autos,
                geoparquet_path,
                overwrite=False,
            )
            logger.info("Wrote autos GeoParquet in %.1f s", perf_counter() - started)
        return AutosBuild(
            target_path=target_path,
            vbo_count=vbo_count,
            buurt_count=buurt_count,
            vbos_with_missing_cbs_data=0,
            buurten_without_control=0,
            reused=True,
            geoparquet_path=written_geoparquet_path,
        )
    if not bag_vbo_path.exists():
        raise FileNotFoundError(f"BAG VBO output {bag_vbo_path} does not exist")
    if not cbs_buurt_path.exists():
        raise FileNotFoundError(f"CBS buurt output {cbs_buurt_path} does not exist")

    started = perf_counter()
    bag_vbo = _read_bag_vbo(bag_vbo_path, layer=bag_vbo_layer)
    cbs_buurten = _read_cbs_autos(
        cbs_buurt_path,
        cbs_buurtgegevens_path,
        layer=cbs_buurt_layer,
    )
    logger.info("Read autos inputs in %.1f s", perf_counter() - started)

    started = perf_counter()
    autos, missing_count, unchecked_buurt_count = bereken_personenautos_per_vbo(
        bag_vbo,
        cbs_buurten,
    )
    logger.info("Calculated and validated autos in %.1f s", perf_counter() - started)

    started = perf_counter()
    write_geopackage_layer_atomically(
        autos,
        target_path,
        layer_name=AUTOS_LAYER,
    )
    logger.info("Wrote autos GeoPackage in %.1f s", perf_counter() - started)
    written_geoparquet_path = None
    if write_geoparquet:
        started = perf_counter()
        written_geoparquet_path = write_geoparquet_atomically(
            autos,
            geoparquet_path,
            overwrite=overwrite,
        )
        logger.info("Wrote autos GeoParquet in %.1f s", perf_counter() - started)
    buurt_count = int(autos[CBS_BUURTCODE_COLUMN].nunique())
    logger.info(
        "Completed autos output with %s VBO's in %s buurten: %s",
        len(autos),
        buurt_count,
        target_path,
    )
    return AutosBuild(
        target_path=target_path,
        vbo_count=len(autos),
        buurt_count=buurt_count,
        vbos_with_missing_cbs_data=missing_count,
        buurten_without_control=unchecked_buurt_count,
        reused=False,
        geoparquet_path=written_geoparquet_path,
    )
