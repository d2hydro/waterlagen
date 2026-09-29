"""Stap 3: gebruiksfunctie kiezen (notitie p. 4-5).

- Kies per VBO het gebruiksdoel met de hoogste prioriteit.
- Splits panden met en zonder woonfunctie en tel niet-woon-VBO's.
- Neem één kandidaatfunctie of uitsluitend overige met NULL direct over.
- Rangschik anders de opgetelde oppervlakten, met uitsluiting van NULL en
  overige gebruiksfunctie onder 100 m².
- Laat ongeldige brongegevens en gelijke grootste resterende totalen open.
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

GOAL_PRIORITY = (
    "gezondheidszorgfunctie",
    "winkelfunctie",
    "kantoorfunctie",
    "industriefunctie",
    "woonfunctie",
    "logiesfunctie",
    "onderwijsfunctie",
    "sportfunctie",
    "bijeenkomstfunctie",
    "celfunctie",
    "overige gebruiksfunctie",
)
KNOWN_GOALS = set(GOAL_PRIORITY)


@dataclass
class _FunctionChoice:
    rule: str
    reason: str
    function: str | None = None
    status: str = "nog te beoordelen"
    areas: str = ""


def _choose_candidate_function(vbo: pd.DataFrame, goals: pd.Series) -> _FunctionChoice:
    """Kies uit niet-woonfuncties; een lege doelwaarde vertegenwoordigt NULL."""
    functions = set(goals)
    if functions == {""}:
        return _FunctionChoice(
            status="geen gebruiksdoel",
            rule="ontbrekend gebruiksdoel",
            reason="Geen gebruiksdoel ingevuld bij de kandidaat-verblijfsobjecten.",
        )
    if len(functions) == 1:
        return _FunctionChoice(
            function=goals.iloc[0],
            status="gekozen",
            rule="één gebruiksdoel",
            reason="Alle kandidaat-verblijfsobjecten hebben dezelfde functie.",
        )
    if functions == {"overige gebruiksfunctie", ""}:
        return _FunctionChoice(
            function="overige gebruiksfunctie",
            status="gekozen",
            rule="overige gebruiksfunctie met NULL",
            reason="Alleen overige gebruiksfunctie en NULL: kies overige gebruiksfunctie ongeacht de oppervlakte.",
        )

    # NULL kan nooit winnen; zijn oppervlakte is niet nodig voor de vergelijking.
    known = goals.ne("")
    vbo = vbo.loc[known]
    goals = goals.loc[known]
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
    ranked = totals.sort_values(ascending=False, kind="stable")
    eligible = ranked[(ranked.index != "overige gebruiksfunctie") | (ranked >= 100)]
    winners = eligible[eligible == eligible.iloc[0]]
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
        reason="Kies de niet-woonfunctie met de grootste opgetelde oppervlakte na uitsluiting van NULL en overige gebruiksfunctie onder 100 m². Woonoppervlakte telt niet mee voor deze keuze, wel voor de bouwlagen.",
        areas=overview,
    )


def _choose_function(vbo: pd.DataFrame) -> _FunctionChoice:
    """Selecteer per VBO één doel en pas daarna de pandregels toe."""
    if vbo.empty:
        return _FunctionChoice(
            status="geen gebruiksdoel",
            rule="geen verblijfsobject",
            reason="Geen gekoppeld verblijfsobject in de bron.",
        )
    selected = []
    reasons = []
    for identifier, value in zip(
        vbo["identificatie"], vbo["gebruiksdoel"].fillna(""), strict=True
    ):
        functions = {part.strip().casefold() for part in str(value).split(",")}
        functions.discard("")
        unknown = functions - KNOWN_GOALS
        if unknown:
            return _FunctionChoice(
                rule="ontbrekend of onbekend doel",
                reason=f"VBO {identifier}: onbekend gebruiksdoel: {', '.join(sorted(unknown))}.",
            )
        function = next((goal for goal in GOAL_PRIORITY if goal in functions), "")
        selected.append(function)
        if len(functions) > 1:
            reasons.append(
                f"VBO {identifier}: {', '.join(sorted(functions))} → {function} volgens prioriteit; "
                "het volledige VBO-oppervlak telt eenmaal mee bij de gekozen functie."
            )
    goals = pd.Series(selected, index=vbo.index, dtype="object")
    choice = _choose_building_function(vbo, goals)
    if reasons:
        choice.reason = " ".join([*reasons, choice.reason])
    return choice


def _choose_building_function(vbo: pd.DataFrame, goals: pd.Series) -> _FunctionChoice:
    """Pas de pandregels toe op de geselecteerde enkelvoudige VBO-functies."""
    non_residential = goals != "woonfunctie"
    has_residential = goals.eq("woonfunctie").any()
    if not has_residential:
        return _choose_candidate_function(vbo, goals)

    non_residential_count = int(non_residential.sum())
    if non_residential_count == 0:
        return _FunctionChoice(
            function="woonfunctie",
            status="gekozen",
            rule="één gebruiksdoel",
            reason="Alle gekoppelde verblijfsobjecten hebben dezelfde functie.",
        )
    if len(vbo) >= 4 and non_residential_count == 1:
        return _FunctionChoice(
            function="woonfunctie",
            status="gekozen",
            rule="appartementencomplex met één andere functie",
            reason="Minimaal 4 verblijfsobjecten met wonen en precies één niet-woonverblijfsobject: appartementencomplex.",
        )
    if len(vbo) <= 3 and non_residential_count == 1:
        other = goals[non_residential].iloc[0]
        if other in {"overige gebruiksfunctie", ""}:
            return _FunctionChoice(
                function="woonfunctie",
                status="gekozen",
                rule="wonen met overige gebruiksfunctie of NULL",
                reason="Maximaal 3 verblijfsobjecten met precies één niet-woonverblijfsobject met overige gebruiksfunctie of NULL: woning, ongeacht de oppervlakte.",
            )
        return _FunctionChoice(
            function=other,
            status="gekozen",
            rule="wonen met één andere functie",
            reason="Maximaal 3 verblijfsobjecten, met wonen en precies één niet-woonverblijfsobject. Oppervlakteverhouding is niet bepalend.",
        )

    return _choose_candidate_function(vbo.loc[non_residential], goals[non_residential])


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

    Notes
    -----
    Woonfunctie met maximaal één niet-woon-VBO volgt de woning- en
    appartementenregels. Anders worden kandidaatfuncties per oppervlakte
    opgeteld, zonder woonfunctie. Eén functie en uitsluitend overige met NULL
    worden direct gekozen. Bij rangschikking vallen NULL en overige onder
    100 m² af. Gelijke grootste resterende totalen blijven te beoordelen.
    Meervoudige doelen worden eerst per VBO volgens ``GOAL_PRIORITY`` teruggebracht
    tot één functie. Het volledige VBO-oppervlak telt eenmaal mee bij die functie.
    De geselecteerde functies bepalen ook de aanwezigheid van wonen en de
    aantallen niet-woon-VBO's. Bronwaarden blijven behouden.
    Ontbrekende doelen zijn NULL; onbekende doelen blijven open.
    ``woonfunctie`` wordt in de daaropvolgende gebouwclassificatie op basis
    van het totale VBO-aantal een woning of appartementencomplex.
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
