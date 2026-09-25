"""Stap 3: gebruiksfunctie kiezen (notitie p. 4-5).

- Controleer ontbrekende en meervoudige gebruiksdoelen.
- Neem één gezamenlijk gebruiksdoel over.
- Pas de regel voor wonen met een andere gebruiksfunctie toe.
- Vergelijk anders het vloeroppervlak van de niet-woonfuncties.
- Laat combinaties zonder beslisregel open.
"""

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd

from waterlagen.functioneel_landgebruik.bag_panden_en_verblijfsobjecten import (
    _format_area,
    _group_verblijfsobjecten_by_pand,
    _invalid_area_reason,
    _shared_area_reason,
)

KNOWN_GOALS = {
    "woonfunctie",
    "bijeenkomstfunctie",
    "celfunctie",
    "gezondheidszorgfunctie",
    "industriefunctie",
    "kantoorfunctie",
    "logiesfunctie",
    "onderwijsfunctie",
    "sportfunctie",
    "winkelfunctie",
    "overige gebruiksfunctie",
}


@dataclass
class _FunctionChoice:
    rule: str
    reason: str
    function: str | None = None
    status: str = "nog te beoordelen"
    areas: str = ""


def _choose_largest_non_residential_function(
    vbo: pd.DataFrame, goals: pd.Series
) -> _FunctionChoice:
    """Kies de gebruiksfunctie met het grootste vloeroppervlak.

    - Afspraak: woonfunctie telt niet mee in de vergelijking.
    - Gedeeld oppervlak of gelijke grootste totalen: keuze blijft open.
    """
    # De oppervlakte van een gedeeld VBO is niet per pand uitgesplitst.
    if vbo["pand_identificatie"].str.contains(",", regex=False).any():
        return _FunctionChoice(
            rule="verblijfsobject in meerdere panden",
            reason=_shared_area_reason(vbo),
        )
    areas = pd.to_numeric(vbo["oppervlakte"], errors="coerce")
    if areas.isna().any() or (areas <= 0).any() or not np.isfinite(areas).all():
        return _FunctionChoice(
            rule="oppervlakte ontbreekt of ongeldig",
            reason=_invalid_area_reason(vbo),
        )
    totals = areas.groupby(goals).sum()
    overview = "; ".join(f"{goal}: {area:g} m²" for goal, area in totals.items())
    winners = totals[totals == totals.max()]
    if len(winners) != 1:
        tied = "; ".join(
            f"{goal}: {_format_area(area)}" for goal, area in winners.items()
        )
        return _FunctionChoice(
            rule="gelijke grootste oppervlakten",
            reason=f"{tied}. Gelijke grootste oppervlakte: voorrang nog te bepalen.",
            areas=overview,
        )
    return _FunctionChoice(
        function=str(winners.index[0]),
        status="gekozen",
        rule="grootste niet-woonoppervlakte",
        reason="Minimaal 2 niet-woon-verblijfsobjecten, ook bij meer dan 3 VBO's in het pand. Kies de niet-woonfunctie met de grootste opgetelde oppervlakte. Woonoppervlakte telt niet mee voor deze keuze, wel voor de bouwlagen.",
        areas=overview,
    )


def _multiple_goal_reason(vbo: pd.DataFrame, goals: pd.Series) -> str:
    """Noem alleen de gebruiksdoelen waarvan het gezamenlijke oppervlak niet is verdeeld."""
    shared = goals.str.contains(",", regex=False)
    areas = pd.to_numeric(vbo.loc[shared, "oppervlakte"], errors="coerce")
    reasons = []
    for goal, area in zip(goals.loc[shared], areas, strict=True):
        functions = ", ".join(part.strip() for part in goal.split(","))
        if pd.isna(area) or not np.isfinite(area) or area <= 0:
            reasons.append(f"{functions}: oppervlakte ontbreekt of is ongeldig.")
        else:
            reasons.append(f"{functions}: {_format_area(area)} niet uitgesplitst.")
    return " ".join(dict.fromkeys(reasons))


def _choose_function(vbo: pd.DataFrame) -> _FunctionChoice:
    """Loop de functieregels in vaste volgorde door voor één pand."""
    # 3a. Eerst controleren of de bron een functiekeuze toelaat.
    if vbo.empty:
        return _FunctionChoice(
            status="geen gebruiksdoel",
            rule="geen verblijfsobject",
            reason="Geen gekoppeld verblijfsobject in de bron.",
        )
    goals = vbo["gebruiksdoel"].fillna("").astype(str).str.strip().str.lower()
    if goals.eq("").all():
        return _FunctionChoice(
            status="geen gebruiksdoel",
            rule="ontbrekend gebruiksdoel",
            reason="Geen gebruiksdoel ingevuld bij de gekoppelde verblijfsobjecten.",
        )
    if goals.str.contains(",", regex=False).any():
        return _FunctionChoice(
            rule="meerdere doelen per verblijfsobject",
            reason=_multiple_goal_reason(vbo, goals),
        )
    if not goals.isin(KNOWN_GOALS).all():
        return _FunctionChoice(
            rule="ontbrekend of onbekend doel",
            reason="Gebruiksdoel ontbreekt of is onbekend bij een VBO.",
        )
    # 3b. Eén gebruiksdoel bij alle VBO's: geen oppervlaktevergelijking nodig.
    if goals.nunique() == 1:
        return _FunctionChoice(
            function=goals.iloc[0],
            status="gekozen",
            rule="één gebruiksdoel",
            reason="Alle gekoppelde verblijfsobjecten hebben dezelfde functie.",
        )

    # Afspraak: uitsluitend wonen en overige gebruiksfunctie wordt wonen.
    if set(goals) == {"woonfunctie", "overige gebruiksfunctie"}:
        return _FunctionChoice(
            function="woonfunctie",
            status="gekozen",
            rule="wonen met overige gebruiksfunctie",
            reason="Alleen woonfunctie en overige gebruiksfunctie. Woonfunctie bepaalt de indeling.",
        )

    # 3c. Winkel/wonen-voorbeeld: tot en met 3 VBO's gaat de andere functie voor.
    non_residential = goals != "woonfunctie"
    has_residential = goals.eq("woonfunctie").any()
    non_residential_count = int(non_residential.sum())
    if len(vbo) <= 3 and has_residential and non_residential_count == 1:
        other = goals[non_residential].iloc[0]
        if other != "overige gebruiksfunctie":
            return _FunctionChoice(
                function=other,
                status="gekozen",
                rule="wonen met één andere functie",
                reason="Maximaal 3 verblijfsobjecten, met wonen en precies één niet-woonverblijfsobject. Oppervlakteverhouding is niet bepalend.",
            )

    # Minstens twee niet-woon-VBO's: vergelijk hun oppervlakte per functie.
    # Afgesproken uitwerking: wonen telt hier niet mee, ook bij meer dan 3 VBO's.
    if non_residential_count >= 2:
        return _choose_largest_non_residential_function(
            vbo.loc[non_residential], goals[non_residential]
        )
    counts = " + ".join(
        f"{count} {goal.removesuffix('functie')}-{'VBO' if count == 1 else 'VBO’s'}"
        for goal, count in goals.value_counts().items()
    )
    if len(vbo) > 3:
        reason = f"{counts}: voorrang bij meer dan 3 VBO’s nog te bepalen."
    else:
        reason = f"{counts}: voorrang nog te bepalen."
    return _FunctionChoice(
        rule="combinatie zonder beslisregel",
        reason=reason,
    )


def determine_bag_functions(
    panden: gpd.GeoDataFrame, verblijfsobjecten: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Bepaal de gebruiksfunctie voor de geselecteerde panden.

    Parameters
    ----------
    panden : geopandas.GeoDataFrame
        Panden geselecteerd op gebouwstatus in stap 2.
    verblijfsobjecten : geopandas.GeoDataFrame
        Alle gekoppelde verblijfsobjecten uit stap 1.

    Returns
    -------
    geopandas.GeoDataFrame
        - Gebruiksfunctie, toegepaste regel en reden.
        - Vergeleken vloeroppervlak per gebruiksfunctie.
        - Openstaande keuzes zonder toegewezen gebruiksfunctie.
    """
    grouped = _group_verblijfsobjecten_by_pand(verblijfsobjecten)
    result = panden.copy()
    choices = []
    all_goals = []
    for pand_id in result["identificatie"]:
        objects = grouped.get(str(pand_id), verblijfsobjecten.iloc[:0])
        choices.append(_choose_function(objects))
        goals = {
            part.strip().casefold() or "ontbreekt"
            for value in objects["gebruiksdoel"].fillna("").astype(str)
            for part in value.split(",")
        }
        all_goals.append(",".join(sorted(goals)))
    result["alle_bag_gebruiksdoelen"] = all_goals
    result["gekozen_pandfunctie"] = pd.Series(
        [c.function for c in choices], index=result.index, dtype="object"
    )
    result["functiekeuze_status"] = [c.status for c in choices]
    result["regel_functiekeuze"] = [c.rule for c in choices]
    result["reden_functiekeuze"] = [c.reason for c in choices]
    result["vergeleken_oppervlakten"] = [c.areas for c in choices]
    return result
