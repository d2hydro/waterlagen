"""Stap 4: bepaal het aantal verdiepingen volgens de notitie (p. 4-5).

- Tel het vloeroppervlak van alle verblijfsobjecten op, ook wonen.
- Deel door het volledige pandoppervlak en rond naar boven af.
- De begane grond telt mee; de uitvoerkolommen heten nog 'bouwlagen'.
- Laat ontbrekend oppervlak en gedeelde verblijfsobjecten ter beoordeling.
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from waterlagen._crs import same_crs
from waterlagen.functioneel_landgebruik.bag_panden_en_verblijfsobjecten import (
    _group_verblijfsobjecten_by_pand,
    _invalid_area_reason,
    _shared_area_reason,
)


def determine_bag_floors(
    panden: gpd.GeoDataFrame, verblijfsobjecten: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Bereken het aantal verdiepingen, met behoud van de gekozen gebruiksfunctie.

    Parameters
    ----------
    panden : geopandas.GeoDataFrame
        Geselecteerde, niet afgeknipte panden uit stap 3 in EPSG:28992.
    verblijfsobjecten : geopandas.GeoDataFrame
        Gekoppelde verblijfsobjecten met hun volledige vloeroppervlak uit de bron.

    Returns
    -------
    geopandas.GeoDataFrame
        - Vloeroppervlak, pandoppervlak en de verhouding daartussen.
        - Aantal verdiepingen, naar boven afgerond.
        - Reden als de berekening openblijft.
    """
    if panden.crs is None or not same_crs(panden.crs, "EPSG:28992"):
        raise ValueError("Berekening van het pandoppervlak vereist EPSG:28992.")
    grouped = _group_verblijfsobjecten_by_pand(verblijfsobjecten)

    result = panden.copy()
    result["pandoppervlakte_m2"] = result.geometry.area
    result["som_vbo_oppervlakte_m2"] = np.nan
    result["verhouding_vbo_pand"] = np.nan
    result["berekend_aantal_bouwlagen"] = pd.Series(
        pd.NA, index=result.index, dtype="Int64"
    )
    result["bouwlagen_status"] = "nog te beoordelen"
    result["reden_bouwlagen"] = ""
    for index, pand in result.iterrows():
        objects = grouped.get(str(pand["identificatie"]), verblijfsobjecten.iloc[:0])
        areas = pd.to_numeric(objects["oppervlakte"], errors="coerce")
        footprint = pand["pandoppervlakte_m2"]
        # Eerst bepalen of we een volledige, aan dit pand toe te wijzen som hebben.
        if objects.empty:
            reason = "Geen VBO gekoppeld: vloeroppervlakte onbekend."
        elif objects["pand_identificatie"].str.contains(",", regex=False).any():
            reason = _shared_area_reason(objects)
        elif areas.isna().any() or (areas <= 0).any() or not np.isfinite(areas).all():
            reason = _invalid_area_reason(objects)
        elif not np.isfinite(footprint) or footprint <= 0:
            reason = "Pandoppervlakte ontbreekt of is ongeldig."
        else:
            # Gebruiksfunctie kiezen (stap 3) en verdiepingen berekenen zijn apart.
            # Daarom tellen ook verblijfsobjecten met woonfunctie mee.
            total = areas.sum()
            ratio = total / footprint
            result.at[index, "som_vbo_oppervlakte_m2"] = total
            result.at[index, "verhouding_vbo_pand"] = ratio
            result.at[index, "berekend_aantal_bouwlagen"] = int(np.ceil(ratio))
            result.at[index, "bouwlagen_status"] = "berekend"
            reason = "Som van het oppervlak van de verblijfsobjecten delen door het oppervlak van het pand en naar boven afronden (notitie p. 4-5)."
        result.at[index, "reden_bouwlagen"] = reason
    return result
