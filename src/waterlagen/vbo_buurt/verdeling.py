"""Kleine, gedeelde verdeelbewerkingen voor waarden per woon-VBO."""

import numpy as np
import pandas as pd


def deel_buurtwaarde_per_vbo(
    data: pd.DataFrame,
    *,
    waarde_column: str,
    noemer_column: str,
) -> pd.Series:
    """Divide a buurtwaarde over VBO's without converting no-data to zero.

    Missing values and zero or negative denominators result in ``NaN``.
    """
    waarde = pd.to_numeric(data[waarde_column], errors="coerce")
    noemer = pd.to_numeric(data[noemer_column], errors="coerce")
    result = pd.Series(np.nan, index=data.index, dtype="float64")
    valid = waarde.notna() & noemer.notna() & noemer.gt(0)
    result.loc[valid] = waarde.loc[valid] / noemer.loc[valid]
    return result
