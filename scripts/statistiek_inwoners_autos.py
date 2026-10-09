"""Log CBS- en VBO-totalen voor inwoners en personenauto's."""

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from waterlagen._geopandas import read_file
from waterlagen.autos import AUTOS_LAYER, PERSONENAUTOS_COLUMN
from waterlagen.datastore import DataStore
from waterlagen.inwoners import (
    INWONERS_LAYER,
    INWONERS_OBV_HUISHOUDENS_COLUMN,
    INWONERS_OBV_WOONVBO_COLUMN,
)
from waterlagen.logger import get_logger, init_logger
from waterlagen.vbo_buurt import CBS_BUURT_OUTPUT_LAYER

logger = get_logger(__name__)

CBS_AANTAL_INWONERS_COLUMN = "aantal_inwoners"
CBS_PERSONENAUTOS_TOTAAL_COLUMN = "personenautos_totaal"


@dataclass(frozen=True)
class VerdelingStatistieken:
    """CBS-totalen en sommen van de verdeelde waarden."""

    cbs_aantal_inwoners: int | float | None
    inwoners_obv_huishoudens: int | float | None
    inwoners_obv_woonvbo: int | float | None
    cbs_personenautos_totaal: int | float | None
    personenautos: int | float | None


def _som_kolom(path: Path, *, layer: str, column: str) -> int | float | None:
    """Read and sum one numeric column without loading geometries."""
    if not path.exists():
        raise FileNotFoundError(f"Required processed output {path} does not exist")
    data = read_file(path, layer=layer, columns=[column], ignore_geometry=True)
    if column not in data.columns:
        raise ValueError(f"Layer {layer} in {path} has no required column {column}")
    values = pd.to_numeric(data[column], errors="raise")
    total = values.sum(min_count=1)
    if pd.isna(total):
        return None
    return total


def _verschil(
    verdeelde_waarde: float | None,
    cbs_waarde: float | None,
) -> int | float | None:
    """Return a difference only when both totals are available."""
    if verdeelde_waarde is None or cbs_waarde is None:
        return None
    return verdeelde_waarde - cbs_waarde


def lees_verdelingstatistieken(
    data_store: DataStore,
    *,
    inwoners_path: Path | None = None,
    autos_path: Path | None = None,
) -> VerdelingStatistieken:
    """Read CBS totals and the derived VBO-value sums from processed outputs."""
    cbs_aantal_inwoners = _som_kolom(
        data_store.cbs_buurt_path,
        layer=CBS_BUURT_OUTPUT_LAYER,
        column=CBS_AANTAL_INWONERS_COLUMN,
    )
    cbs_personenautos_totaal = _som_kolom(
        data_store.cbs_buurt_path,
        layer=CBS_BUURT_OUTPUT_LAYER,
        column=CBS_PERSONENAUTOS_TOTAAL_COLUMN,
    )
    inwoners_obv_huishoudens = _som_kolom(
        inwoners_path or data_store.inwoners_path,
        layer=INWONERS_LAYER,
        column=INWONERS_OBV_HUISHOUDENS_COLUMN,
    )
    inwoners_obv_woonvbo = _som_kolom(
        inwoners_path or data_store.inwoners_path,
        layer=INWONERS_LAYER,
        column=INWONERS_OBV_WOONVBO_COLUMN,
    )
    personenautos = _som_kolom(
        autos_path or data_store.autos_path,
        layer=AUTOS_LAYER,
        column=PERSONENAUTOS_COLUMN,
    )
    return VerdelingStatistieken(
        cbs_aantal_inwoners=cbs_aantal_inwoners,
        inwoners_obv_huishoudens=inwoners_obv_huishoudens,
        inwoners_obv_woonvbo=inwoners_obv_woonvbo,
        cbs_personenautos_totaal=cbs_personenautos_totaal,
        personenautos=personenautos,
    )


def main(
    data_store: DataStore | None = None,
    *,
    inwoners_path: Path | None = None,
    autos_path: Path | None = None,
) -> VerdelingStatistieken:
    """Log CBS- en VBO-totalen for the inwoners and autos products."""
    data_store = data_store or DataStore()
    init_logger(
        name="statistiek_inwoners_autos",
        debug=False,
        log_file=data_store.data_dir / "statistiek_inwoners_autos.log",
    )
    statistieken = lees_verdelingstatistieken(
        data_store, inwoners_path=inwoners_path, autos_path=autos_path
    )
    logger.info("CBS aantal_inwoners: %s", statistieken.cbs_aantal_inwoners)
    logger.info(
        "Som inwoners_obv_huishoudens: %s (verschil met CBS: %s)",
        statistieken.inwoners_obv_huishoudens,
        _verschil(
            statistieken.inwoners_obv_huishoudens,
            statistieken.cbs_aantal_inwoners,
        ),
    )
    logger.info(
        "Som inwoners_obv_woonvbo: %s (verschil met CBS: %s)",
        statistieken.inwoners_obv_woonvbo,
        _verschil(
            statistieken.inwoners_obv_woonvbo,
            statistieken.cbs_aantal_inwoners,
        ),
    )
    logger.info("CBS personenautos_totaal: %s", statistieken.cbs_personenautos_totaal)
    logger.info(
        "Som personenautos: %s (verschil met CBS: %s)",
        statistieken.personenautos,
        _verschil(
            statistieken.personenautos,
            statistieken.cbs_personenautos_totaal,
        ),
    )
    return statistieken


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inwoners-path", type=Path, help="Inwoners-GeoPackage uit de gekozen run"
    )
    parser.add_argument(
        "--autos-path", type=Path, help="Auto-GeoPackage uit de gekozen run"
    )
    main(**vars(parser.parse_args()))
