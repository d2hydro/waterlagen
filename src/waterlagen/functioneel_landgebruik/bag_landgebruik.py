"""Stap 5: categorie gebouw bepalen (notitie, tabel 1).

- Gebruik de gekozen gebruiksfunctie en het aantal verdiepingen.
- Pas aparte regels toe voor appartementencomplex en overige gebruiksfunctie.
- Lees de codes voor binnendijks en buitendijks uit de CSV.
- Laat onopgeloste functiekeuzes open.
"""

import geopandas as gpd
import pandas as pd

from waterlagen.functioneel_landgebruik.landgebruikstabel import (
    LanduseMapping,
    LanduseTable,
    load_landuse_table,
)

# Vaste verwijzingen naar CSV-rijen, met de benamingen uit tabel 1 (notitie p. 3).
# De binnen- en buitencodes worden uit die rijen gelezen, niet hier berekend.
FLOOR_MAPPING_IDS = {
    "woonfunctie": {
        "enkel begane grond": "BAG-001",
        "begane grond en eerste verdieping": "BAG-002",
        "meer dan 2 verdiepingen": "BAG-003",
    },
    "bijeenkomstfunctie": {
        "enkel begane grond": "BAG-004",
        "begane grond en eerste verdieping": "BAG-005",
        "meer dan 2 verdiepingen": "BAG-006",
    },
    "celfunctie": {
        "enkel begane grond": "BAG-007",
        "begane grond en eerste verdieping": "BAG-008",
        "meer dan 2 verdiepingen": "BAG-009",
    },
    "gezondheidszorgfunctie": {
        "enkel begane grond": "BAG-010",
        "begane grond en eerste verdieping": "BAG-011",
        "meer dan 2 verdiepingen": "BAG-012",
    },
    "industriefunctie": {
        "enkel begane grond": "BAG-013",
        "begane grond en eerste verdieping": "BAG-014",
        "meer dan 2 verdiepingen": "BAG-015",
    },
    "kantoorfunctie": {
        "enkel begane grond": "BAG-016",
        "begane grond en eerste verdieping": "BAG-017",
        "meer dan 2 verdiepingen": "BAG-018",
    },
    "logiesfunctie": {
        "enkel begane grond": "BAG-019",
        "begane grond en eerste verdieping": "BAG-020",
        "meer dan 2 verdiepingen": "BAG-021",
    },
    "onderwijsfunctie": {
        "enkel begane grond": "BAG-022",
        "begane grond en eerste verdieping": "BAG-023",
        "meer dan 2 verdiepingen": "BAG-024",
    },
    "sportfunctie": {
        "enkel begane grond": "BAG-025",
        "begane grond en eerste verdieping": "BAG-026",
        "meer dan 2 verdiepingen": "BAG-027",
    },
    "winkelfunctie": {
        "enkel begane grond": "BAG-028",
        "begane grond en eerste verdieping": "BAG-029",
        "meer dan 2 verdiepingen": "BAG-030",
    },
}


def _validated_bag_mappings(table: LanduseTable) -> dict[str, LanduseMapping]:
    """Controleer vaste ID's op bron en functie; codes en omschrijvingen zijn vrij."""
    expected_functions = {}
    for function, floor_mappings in FLOOR_MAPPING_IDS.items():
        for mapping_id in floor_mappings.values():
            expected_functions[mapping_id] = function
    expected_functions.update(
        {
            "BAG-031": "woonfunctie",  # Appartementencomplex.
            "BAG-032": "overige gebruiksfunctie",  # Meer dan 100 m².
            "BAG-033": "overige gebruiksfunctie",  # Maximaal 100 m².
            "BAG-034": None,  # Aparte bronwaarde voor ontbrekend gebruiksdoel.
        }
    )
    mappings = {}
    for mapping_id, expected_function in expected_functions.items():
        mapping = table.by_id(mapping_id)
        if mapping.source != "BAG":
            raise ValueError(
                f"CSV {table.path}: {mapping_id} verwacht bron BAG, "
                f"maar heeft bron {mapping.source!r}."
            )
        if expected_function is not None and mapping.values != (expected_function,):
            raise ValueError(
                f"CSV {table.path}: {mapping_id} verwacht Bronwaarde "
                f"{expected_function!r}, maar heeft {mapping.values!r}. "
                "Geef een bestaande koppeling-ID geen andere functie."
            )
        mappings[mapping_id] = mapping
    return mappings


def determine_bag_classes(
    panden: gpd.GeoDataFrame, *, table: LanduseTable | None = None
) -> gpd.GeoDataFrame:
    """Koppel de resultaten van stap 4 aan een categorie gebouw.

    Parameters
    ----------
    panden : geopandas.GeoDataFrame
        Panden met gebruiksfunctie, aantal verblijfsobjecten en verdiepingen.
    table : LanduseTable, optional
        CSV met codes en omschrijvingen; standaard de meegeleverde tabel.

    Returns
    -------
    geopandas.GeoDataFrame
        - Categorie gebouw en beide landgebruikscodes.
        - Reden van indeling of openstaande keuze.
        - Oorspronkelijke pandgegevens.

    Raises
    ------
    ValueError
        Een CSV-koppeling ontbreekt of heeft een verkeerde bron of gebruiksfunctie.
    """
    table = table or load_landuse_table()
    mappings = _validated_bag_mappings(table)
    result = panden.copy()
    for column in ["lgb_code_binnendijks", "lgb_code_buitendijks"]:
        result[column] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    result["lgb_omschrijving"] = pd.Series(None, index=result.index, dtype="object")
    result["lgb_koppeling_id"] = pd.Series(None, index=result.index, dtype="object")
    result["klasse_status"] = "nog te beoordelen"
    result["reden_klasse"] = ""
    for index, pand in result.iterrows():
        function = pand["gekozen_pandfunctie"]
        count = pand["bron_aantal_vbo"]
        floors = pand["berekend_aantal_bouwlagen"]
        mapping_id = None
        # Geen gebruiksdoel is een eigen categorie. Een onopgeloste keuze niet.
        if pand["functiekeuze_status"] == "geen gebruiksdoel":
            mapping_id = "BAG-034"
            reason = "Geen gebruiksdoel in stap 3; aparte categorie uit tabel 1."
        elif pand["functiekeuze_status"] != "gekozen" or pd.isna(function):
            reason = "Gebruiksfunctie nog te bepalen."
        elif function == "woonfunctie" and pd.notna(count) and count >= 4:
            mapping_id = "BAG-031"
            reason = (
                "Gekozen woonfunctie met 4 of meer verblijfsobjecten (notitie p. 4)."
            )
        elif function == "overige gebruiksfunctie":
            # Uitsluitend overige gebruiksfunctie: toets totaal vloeroppervlak aan 100 m².
            area = pand["som_vbo_oppervlakte_m2"]
            only_other_use = (
                pand.get("alle_bag_gebruiksdoelen", "") == "overige gebruiksfunctie"
            )
            if count != 1 and not only_other_use:
                reason = "Gemengde functies: toepassing 100 m²-grens nog te bepalen."
            elif pd.isna(area) or area <= 0:
                reason = "100 m²-grens: VBO-oppervlakte ontbreekt of is ongeldig."
            else:
                if area > 100:
                    mapping_id = "BAG-032"
                else:
                    mapping_id = "BAG-033"
                reason = "Som van de VBO-oppervlakten bij uitsluitend overige gebruiksfunctie vergeleken met 100 m2: boven 100 m2 groot, anders klein."
        elif function not in FLOOR_MAPPING_IDS:
            reason = "Geen gebouwklasse voor deze gebruiksfunctie."
        elif function == "woonfunctie" and (pd.isna(count) or count < 1):
            reason = "Aantal VBO’s ontbreekt: woning of appartementencomplex onbekend."
        elif pd.isna(floors) or floors < 1:
            reason = "Aantal bouwlagen ontbreekt."
        else:
            # De berekening in stap 4 telt de begane grond mee.
            if int(floors) == 1:
                floor_class = "enkel begane grond"
            elif int(floors) == 2:
                floor_class = "begane grond en eerste verdieping"
            else:
                floor_class = "meer dan 2 verdiepingen"
            mapping_id = FLOOR_MAPPING_IDS[function][floor_class]
            reason = "Gekozen gebruiksfunctie uit stap 3 en berekend aantal verdiepingen uit stap 4 gekoppeld aan tabel 1."
        if mapping_id is not None:
            # Binnen- en buitendijkse code beide uit de CSV; ligging volgt later.
            mapping = mappings[mapping_id]
            result.at[index, "lgb_code_binnendijks"] = mapping.inside
            result.at[index, "lgb_code_buitendijks"] = mapping.outside
            result.at[index, "lgb_omschrijving"] = mapping.description
            result.at[index, "lgb_koppeling_id"] = mapping_id
            result.at[index, "klasse_status"] = "ingedeeld"
        result.at[index, "reden_klasse"] = reason
    return result
