"""Build the shared processed BAG VBO-to-CBS-buurt dataset."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

from waterlagen import datastore
from waterlagen._crs import read_layer_crs_info, same_crs
from waterlagen._downloads import validate_geopackage
from waterlagen._geopackage import write_geopackage_layer
from waterlagen._geopandas import read_file
from waterlagen.administratieve_gebieden import (
    CBS_BUURTCODE_COLUMN,
    CBS_BUURTEN_LAYER,
    wijk_buurtkaart_2025_path,
)
from waterlagen.cbs import buurtgegevens_2025_path
from waterlagen.logger import get_logger

logger = get_logger(__name__)

BAG_LIGHT_FILENAME = "bag-light.gpkg"
BAG_VERBLIJFSOBJECT_LAYER = "verblijfsobject"
BAG_VBO_LAYER = "bag_vbo"
CBS_BUURT_OUTPUT_LAYER = "cbs_buurt"
VBO_ID_COLUMN = "identificatie"
PAND_ID_COLUMN = "pand_identificatie"
STATUS_COLUMN = "status"
GEBRUIKSDOEL_COLUMN = "gebruiksdoel"
AANTAL_WOONVBO_COLUMN = "aantal_woonvbo"
BAG_VBO_COLUMNS = (
    VBO_ID_COLUMN,
    PAND_ID_COLUMN,
    STATUS_COLUMN,
    GEBRUIKSDOEL_COLUMN,
    CBS_BUURTCODE_COLUMN,
    "geometry",
)
CBS_BUURT_COLUMNS = (
    CBS_BUURTCODE_COLUMN,
    "aantal_inwoners",
    "aantal_huishoudens",
    AANTAL_WOONVBO_COLUMN,
    "geometry",
)


class BuurtKoppelingError(ValueError):
    """Raised when BAG features cannot be unambiguously linked to one buurt."""


@dataclass(frozen=True)
class VboBuurtBuild:
    """Counts and output location for one shared VBO-buurt processing run."""

    bag_vbo_path: Path
    cbs_buurt_path: Path
    source_vbo_count: int | None
    selected_woonvbo_count: int
    buurt_count: int
    reused: bool


def _required_columns(data: gpd.GeoDataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in data.columns]
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"Missing required BAG VBO column(s): {names}")


def _has_woonfunctie(value: object) -> bool:
    """Return whether one BAG gebruiksdoel value contains ``woonfunctie``."""
    if value is None:
        return False
    return any(
        gebruiksdoel.strip().lower() == "woonfunctie"
        for gebruiksdoel in str(value).split(",")
    )


def selecteer_woonverblijfsobjecten(
    verblijfsobjecten: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Select BAG VBO's in use whose gebruiksdoel contains woonfunctie.

    Parameters
    ----------
    verblijfsobjecten : geopandas.GeoDataFrame
        BAG verblijfsobjecten with at least ``identificatie``, ``status``,
        ``gebruiksdoel`` and point geometry. ``pand_identificatie`` is retained
        when supplied.

    Returns
    -------
    geopandas.GeoDataFrame
        Copy containing only VBO's with status ``Verblijfsobject in gebruik``
        and a ``woonfunctie`` among one or more comma-separated gebruiksdoelen.
    """
    _required_columns(
        verblijfsobjecten,
        (VBO_ID_COLUMN, STATUS_COLUMN, GEBRUIKSDOEL_COLUMN),
    )
    if verblijfsobjecten.crs is None:
        raise ValueError("BAG verblijfsobjecten have no CRS")
    if verblijfsobjecten[VBO_ID_COLUMN].isna().any():
        raise ValueError("BAG verblijfsobjecten contain VBO's without identificatie")
    if verblijfsobjecten[VBO_ID_COLUMN].duplicated().any():
        raise ValueError("BAG verblijfsobjecten contain duplicate identificaties")

    status_in_gebruik = (
        verblijfsobjecten[STATUS_COLUMN]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.casefold()
        == "verblijfsobject in gebruik"
    )
    woonfunctie = verblijfsobjecten[GEBRUIKSDOEL_COLUMN].map(_has_woonfunctie)
    selected = verblijfsobjecten[status_in_gebruik & woonfunctie].copy()
    logger.info(
        "Selected %s woon-VBO's from %s BAG verblijfsobjecten",
        len(selected),
        len(verblijfsobjecten),
    )
    return selected


def _read_bag_woonverblijfsobjecten(
    bag_path: Path,
    *,
    layer: str,
) -> tuple[gpd.GeoDataFrame, int]:
    """Read only candidate BAG VBO source fields and select woon-VBO's."""
    if not bag_path.exists():
        raise FileNotFoundError(
            f"BAG source GeoPackage {bag_path} does not exist. "
            "Download it with waterlagen.bag.download_bag_light()."
        )

    info = pyogrio.read_info(bag_path, layer=layer)
    source_vbo_count = int(info["features"])
    available_columns = {str(column) for column in info["fields"]}
    required_columns = {VBO_ID_COLUMN, STATUS_COLUMN, GEBRUIKSDOEL_COLUMN}
    missing_columns = required_columns - available_columns
    if missing_columns:
        names = ", ".join(sorted(missing_columns))
        raise ValueError(f"BAG VBO layer {layer} has no required column(s): {names}")

    columns = [VBO_ID_COLUMN, STATUS_COLUMN, GEBRUIKSDOEL_COLUMN]
    if PAND_ID_COLUMN in available_columns:
        columns.append(PAND_ID_COLUMN)
    candidates = read_file(
        bag_path,
        layer=layer,
        columns=columns,
        where=(
            "status = 'Verblijfsobject in gebruik' "
            "AND gebruiksdoel LIKE '%woonfunctie%'"
        ),
    )
    selected = selecteer_woonverblijfsobjecten(candidates)
    logger.info(
        "BAG VBO count before filtering: %s; selected woon-VBO count: %s",
        source_vbo_count,
        len(selected),
    )
    return selected, source_vbo_count


def koppel_features_aan_buurten(
    features: gpd.GeoDataFrame,
    buurten: gpd.GeoDataFrame,
    *,
    feature_id_column: str,
    buurtcode_column: str = CBS_BUURTCODE_COLUMN,
) -> gpd.GeoDataFrame:
    """Link features to one CBS buurt, rejecting incomplete or ambiguous joins.

    The function deliberately does not select an arbitrary result for a feature
    on a boundary. It logs unmatched and multi-matched feature counts and raises
    :class:`BuurtKoppelingError` when either count is nonzero.

    Parameters
    ----------
    features : geopandas.GeoDataFrame
        Features with unique identifiers and a defined CRS.
    buurten : geopandas.GeoDataFrame
        CBS buurt geometries with a unique buurtcode and the same CRS.
    feature_id_column : str
        Identifier column used to check spatial-join cardinality.
    buurtcode_column : str, optional
        CBS buurtcode column, by default ``buurtcode``.

    Returns
    -------
    geopandas.GeoDataFrame
        Features with a non-null, unambiguous CBS buurtcode.
    """
    _required_columns(features, (feature_id_column,))
    _required_columns(buurten, (buurtcode_column,))
    if features.crs is None or buurten.crs is None:
        raise ValueError("Features and CBS buurten must both have a CRS")
    if not same_crs(features.crs, buurten.crs):
        raise ValueError("Features and CBS buurten must use the same CRS")
    if features[feature_id_column].isna().any():
        raise ValueError("Features contain missing identifiers")
    if features[feature_id_column].duplicated().any():
        raise ValueError("Features contain duplicate identifiers")
    if buurten[buurtcode_column].isna().any():
        raise ValueError("CBS buurten contain missing buurtcodes")
    if buurten[buurtcode_column].duplicated().any():
        raise ValueError("CBS buurten contain duplicate buurtcodes")

    buurt_geometries = buurten[[buurtcode_column, "geometry"]].copy()
    joined = gpd.sjoin(
        features,
        buurt_geometries,
        how="left",
        predicate="within",
    ).drop(columns="index_right")
    unmatched_count = int(joined[buurtcode_column].isna().sum())
    duplicate_matches = joined[feature_id_column].duplicated(keep=False)
    multiple_match_count = int(
        joined.loc[duplicate_matches, feature_id_column].nunique()
    )

    logger.info(
        "CBS buurt join exceptions: %s unmatched, %s multiple matches",
        unmatched_count,
        multiple_match_count,
    )

    if unmatched_count:
        logger.warning("%s features have no CBS buurt match", unmatched_count)
    if multiple_match_count:
        logger.warning(
            "%s features have multiple CBS buurt matches", multiple_match_count
        )
    if unmatched_count or multiple_match_count:
        raise BuurtKoppelingError(
            "CBS buurt join is incomplete or ambiguous: "
            f"{unmatched_count} unmatched, {multiple_match_count} multiple matches"
        )

    logger.info("Linked %s features to exactly one CBS buurt", len(joined))
    return joined


def _bag_vbo_columns(features: gpd.GeoDataFrame) -> list[str]:
    return [column for column in BAG_VBO_COLUMNS if column in features.columns]


def _read_cbs_buurtgegevens(path: Path) -> pd.DataFrame:
    """Read required StatLine values while retaining CBS missing values."""
    if not path.exists():
        raise FileNotFoundError(
            f"CBS buurtgegevens {path} do not exist. "
            "Download them with waterlagen.cbs.download_buurtgegevens_2025()."
        )
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("CBS buurtgegevens have no rows list")
    data = pd.DataFrame(rows)
    required_columns = [
        CBS_BUURTCODE_COLUMN,
        "aantal_inwoners",
        "aantal_huishoudens",
    ]
    missing_columns = [column for column in required_columns if column not in data]
    if missing_columns:
        names = ", ".join(missing_columns)
        raise ValueError(f"CBS buurtgegevens have no required column(s): {names}")
    if data[CBS_BUURTCODE_COLUMN].isna().any():
        raise ValueError("CBS buurtgegevens contain missing buurtcodes")
    if data[CBS_BUURTCODE_COLUMN].duplicated().any():
        raise ValueError("CBS buurtgegevens contain duplicate buurtcodes")
    return data[required_columns].copy()


def _bouw_cbs_buurt(
    buurten: gpd.GeoDataFrame,
    bag_vbo: gpd.GeoDataFrame,
    cbs_buurtgegevens: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """Add VBO counts and selected StatLine values to CBS buurt polygons."""
    counts = (
        bag_vbo.groupby(CBS_BUURTCODE_COLUMN)[VBO_ID_COLUMN]
        .size()
        .rename(AANTAL_WOONVBO_COLUMN)
        .reset_index()
    )
    result = buurten[[CBS_BUURTCODE_COLUMN, "geometry"]].merge(
        cbs_buurtgegevens,
        on=CBS_BUURTCODE_COLUMN,
        how="left",
        validate="one_to_one",
    )
    result = result.merge(
        counts,
        on=CBS_BUURTCODE_COLUMN,
        how="left",
        validate="one_to_one",
    )
    result[AANTAL_WOONVBO_COLUMN] = (
        result[AANTAL_WOONVBO_COLUMN].fillna(0).astype("int64")
    )
    result = gpd.GeoDataFrame(result, geometry="geometry", crs=buurten.crs)
    return result[list(CBS_BUURT_COLUMNS)].copy()


def _write_geopackage(
    features: gpd.GeoDataFrame,
    target_path: Path,
    *,
    layer_name: str,
) -> None:
    """Write and validate one output layer before atomically replacing it."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=".gpkg",
        dir=target_path.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink(missing_ok=True)
    try:
        write_geopackage_layer(
            features,
            temporary_path,
            layer_name=layer_name,
            mode="w",
        )
        validate_geopackage(temporary_path)
        layer_info = read_layer_crs_info(temporary_path)
        output_layer = next(
            (info for info in layer_info if info.layer == layer_name),
            None,
        )
        if output_layer is None or output_layer.crs is None:
            raise ValueError("Written VBO-buurt layer has no CRS")
        if not same_crs(features.crs, output_layer.crs):
            raise ValueError("Written VBO-buurt layer has a changed CRS")
        temporary_path.replace(target_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _read_bag_vbo_counts(path: Path) -> tuple[int, int]:
    """Read cached BAG VBO and buurt counts without loading geometries."""
    data = read_file(
        path,
        layer=BAG_VBO_LAYER,
        columns=[VBO_ID_COLUMN, CBS_BUURTCODE_COLUMN],
        ignore_geometry=True,
    )
    return len(data), int(data[CBS_BUURTCODE_COLUMN].nunique())


def bouw_vbo_buurt(
    bag_path: Path = datastore.bag_dir / BAG_LIGHT_FILENAME,
    buurtkaart_path: Path = wijk_buurtkaart_2025_path(),
    cbs_buurtgegevens_path: Path = buurtgegevens_2025_path(),
    *,
    bag_vbo_path: Path = datastore.bag_vbo_path,
    cbs_buurt_path: Path = datastore.cbs_buurt_path,
    bag_vbo_layer: str = BAG_VERBLIJFSOBJECT_LAYER,
    overwrite: bool = True,
) -> VboBuurtBuild:
    """Build separate BAG VBO and CBS buurt processed GeoPackages.

    ``bag_vbo.gpkg`` keeps the selected BAG VBO geometry and its CBS buurtcode.
    ``cbs_buurt.gpkg`` keeps CBS buurt polygons and contains the selected
    StatLine values plus the count of selected woon-VBO's in each buurt.

    Parameters
    ----------
    bag_path : Path, optional
        Existing BAG GeoPackage, by default the downloaded ``bag-light.gpkg``.
    buurtkaart_path : Path, optional
        Existing CBS Wijk- en Buurtkaart 2025 GeoPackage.
    cbs_buurtgegevens_path : Path, optional
        Selected CBS StatLine buurtgegevens JSON source.
    bag_vbo_path : Path, optional
        Processed BAG VBO output GeoPackage.
    cbs_buurt_path : Path, optional
        Processed CBS buurt polygon output GeoPackage.
    bag_vbo_layer : str, optional
        BAG VBO layer name, by default ``verblijfsobject``.
    overwrite : bool, optional
        Whether to replace existing processed outputs. When False, both outputs
        are reused without reading BAG or CBS source data.

    Returns
    -------
    VboBuurtBuild
        Output paths and source, selection and buurt counts.
    """
    bag_path = Path(bag_path)
    buurtkaart_path = Path(buurtkaart_path)
    cbs_buurtgegevens_path = Path(cbs_buurtgegevens_path)
    bag_vbo_path = Path(bag_vbo_path)
    cbs_buurt_path = Path(cbs_buurt_path)
    output_paths = (bag_vbo_path, cbs_buurt_path)
    existing_paths = [path for path in output_paths if path.exists()]
    if existing_paths and not overwrite and len(existing_paths) != len(output_paths):
        raise FileExistsError(
            "Only one VBO-buurt output exists. Use overwrite=True to rebuild both outputs."
        )
    if len(existing_paths) == len(output_paths) and not overwrite:
        selected_woonvbo_count, buurt_count = _read_bag_vbo_counts(bag_vbo_path)
        logger.info("Reusing BAG VBO output from %s", bag_vbo_path)
        logger.info("Reusing CBS buurt output from %s", cbs_buurt_path)
        return VboBuurtBuild(
            bag_vbo_path=bag_vbo_path,
            cbs_buurt_path=cbs_buurt_path,
            source_vbo_count=None,
            selected_woonvbo_count=selected_woonvbo_count,
            buurt_count=buurt_count,
            reused=True,
        )

    woonvbo, source_vbo_count = _read_bag_woonverblijfsobjecten(
        bag_path,
        layer=bag_vbo_layer,
    )
    buurten = read_file(
        buurtkaart_path,
        layer=CBS_BUURTEN_LAYER,
        columns=[CBS_BUURTCODE_COLUMN],
    )
    gekoppeld = koppel_features_aan_buurten(
        woonvbo,
        buurten,
        feature_id_column=VBO_ID_COLUMN,
    )
    bag_vbo = gekoppeld[_bag_vbo_columns(gekoppeld)].copy()
    cbs_buurtgegevens = _read_cbs_buurtgegevens(cbs_buurtgegevens_path)
    cbs_buurt = _bouw_cbs_buurt(buurten, bag_vbo, cbs_buurtgegevens)
    _write_geopackage(bag_vbo, bag_vbo_path, layer_name=BAG_VBO_LAYER)
    _write_geopackage(cbs_buurt, cbs_buurt_path, layer_name=CBS_BUURT_OUTPUT_LAYER)
    buurt_count = int(bag_vbo[CBS_BUURTCODE_COLUMN].nunique())
    logger.info(
        "Completed BAG VBO output with %s woon-VBO's in %s buurten: %s",
        len(bag_vbo),
        buurt_count,
        bag_vbo_path,
    )
    return VboBuurtBuild(
        bag_vbo_path=bag_vbo_path,
        cbs_buurt_path=cbs_buurt_path,
        source_vbo_count=source_vbo_count,
        selected_woonvbo_count=len(bag_vbo),
        buurt_count=buurt_count,
        reused=False,
    )
