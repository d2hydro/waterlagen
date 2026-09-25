"""Editable CSV contracts, legacy compatibility and deterministic presentation."""

import csv
import random
from pathlib import Path
from xml.etree import ElementTree as ET

import geopandas as gpd
import pytest
from shapely.geometry import box

from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import (
    _assign_source_codes,
    prepare_bgt_layer,
)
from waterlagen.functioneel_landgebruik.landgebruikstabel import (
    BUILTIN_RULE_IDS,
    DEFAULT_MAPPING_CSV,
    HEADER_ALIASES,
    MAPPING_FIELDS,
    load_landuse_table,
)
from waterlagen.functioneel_landgebruik.legenda import build_colormap, write_qgis_style

LEGACY_CSV = Path(__file__).parent / "fixtures" / "landgebruik_legacy.csv"


@pytest.fixture
def rows():
    with DEFAULT_MAPPING_CSV.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def write_table(tmp_path, rows):
    path = tmp_path / "mapping.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_bundled_table_and_legacy_have_same_classification():
    assert DEFAULT_MAPPING_CSV.read_bytes().startswith(b"\xef\xbb\xbf")
    table = load_landuse_table()
    legacy = load_landuse_table(LEGACY_CSV)
    assert all(len(row.values) == 1 for row in table.rows)
    assert {
        row.ids[0] for row in table.rows if row.method == "functie"
    } == BUILTIN_RULE_IDS
    assert all(not row.ids for row in table.rows if row.method == "mapping")
    for source, layer in MAPPING_FIELDS:
        new_codes = {
            key: (row.inside, row.outside, row.description, row.field)
            for key, row in table.source_values(source, layer).items()
        }
        old_codes = {
            key: (row.inside, row.outside, row.description, row.field)
            for key, row in legacy.source_values(source, layer).items()
        }
        assert new_codes == old_codes
    for key in BUILTIN_RULE_IDS:
        new_row = table.by_id(key)
        old_row = legacy.by_id(key)
        assert (new_row.inside, new_row.outside, new_row.description) == (
            old_row.inside,
            old_row.outside,
            old_row.description,
        )
    assert build_colormap(table) == build_colormap(legacy)


@pytest.mark.parametrize("mode", ["aliases", "both"])
def test_header_aliases(tmp_path, rows, mode):
    for row in rows:
        for name, alias in HEADER_ALIASES.items():
            row[alias] = row[name]
            if mode == "aliases":
                del row[name]
    assert (
        load_landuse_table(write_table(tmp_path, rows)).rows
        == load_landuse_table().rows
    )


@pytest.mark.parametrize("name,alias", HEADER_ALIASES.items())
def test_conflicting_aliases(tmp_path, rows, name, alias):
    for row in rows:
        row[alias] = row[name]
    rows[0][alias] = "conflict"
    with pytest.raises(ValueError, match="conflicterende kolommen"):
        load_landuse_table(write_table(tmp_path, rows))


@pytest.mark.parametrize(
    "value", ["", "woonfunctie\nwinkelfunctie", "woonfunctie\n\nextra"]
)
def test_new_schema_requires_one_value(tmp_path, rows, value):
    rows[0]["Bronwaarde"] = value
    with pytest.raises(ValueError, match="één Bronwaarde"):
        load_landuse_table(write_table(tmp_path, rows))


@pytest.mark.parametrize(
    "changes,match",
    [
        ({"Koppelmethode": "python"}, "Koppelmethode"),
        ({"Koppel-ID": "custom.module:run"}, "bekend Koppel-ID"),
        ({"Koppel-ID": ""}, "bekend Koppel-ID"),
        ({"Bron": "BGT"}, "bron BAG"),
        ({"Bronwaarde": "winkelfunctie"}, "woonfunctie"),
        ({"Koppelmethode": "mapping"}, "vereist Koppelmethode functie"),
    ],
)
def test_function_identity(tmp_path, rows, changes, match):
    rows[0].update(changes)
    with pytest.raises(ValueError, match=match):
        load_landuse_table(write_table(tmp_path, rows))


def test_function_outputs_are_editable(tmp_path, rows):
    rows[0].update(
        {
            "LGB-code_binnendijks": "110",
            "LGB-code_buitendijks": "240",
            "LGB_beschrijving": "Eigen woning",
        }
    )
    row = load_landuse_table(write_table(tmp_path, rows)).by_id("BAG-001")
    assert (row.inside, row.outside, row.description) == (110, 240, "Eigen woning")


@pytest.mark.parametrize(
    "column,value",
    [
        ("Bron", "CUSTOM"),
        ("Bronlaag", "another_layer"),
        ("Bronveld", "another_field"),
        ("Bronveld", ""),
        ("Bronwaarde", "0"),
        ("Bronwaarde", "1.5"),
    ],
)
def test_unsupported_mapping(tmp_path, rows, column, value):
    row = next(row for row in rows if row["Bron"] == "BRP")
    row[column] = value
    with pytest.raises(ValueError, match="niet ondersteunde|BRP-bronwaarde"):
        load_landuse_table(write_table(tmp_path, rows))


@pytest.mark.parametrize("wildcard", [False, True])
def test_duplicate_mappings(tmp_path, rows, wildcard):
    row = next(
        row
        for row in rows
        if row["Bron"] == "BRP" and (row["Bronwaarde"] == "*") == wildcard
    )
    duplicate = row.copy()
    if not wildcard:
        duplicate["Bronwaarde"] = "0" + row["Bronwaarde"]
    rows.append(duplicate)
    with pytest.raises(ValueError, match="Dubbele bronwaarde"):
        load_landuse_table(write_table(tmp_path, rows))


def test_duplicate_function_ids(tmp_path, rows):
    rows.append(rows[0].copy())
    with pytest.raises(ValueError, match="dubbel Koppel-ID"):
        load_landuse_table(write_table(tmp_path, rows))


def test_brp_fallback_only_for_valid_integer_values(tmp_path, rows):
    random.Random(4).shuffle(rows)
    table = load_landuse_table(write_table(tmp_path, rows))
    values = [
        265,
        "265",
        "265.0",
        99999,
        None,
        "",
        " ",
        "abc",
        0,
        -1,
        1.5,
        float("inf"),
    ]
    data = gpd.GeoDataFrame(
        {"gewascode": values},
        geometry=[box(i, 0, i + 1, 1) for i in range(len(values))],
        crs=28992,
    )
    result = _assign_source_codes(
        data,
        table.source_values("BRP", "brp_gewas"),
        field="gewascode",
        numeric_values=True,
        dike_area=None,
    )
    assert result.index.tolist() == [0, 1, 2, 3]
    assert result["code"].tolist() == [50, 50, 50, 53]


@pytest.mark.parametrize(
    "source,layer,field,explicit",
    [
        (
            "TOP10NL",
            "top10nl_functioneel_gebied_vlak",
            "typefunctioneelgebied",
            "volkstuinen",
        ),
        ("BGT", "bgt_wegdeel", "bgt-functie", "voetpad"),
    ],
)
def test_text_fallback_excludes_empty_values(
    tmp_path, rows, source, layer, field, explicit
):
    row = next(
        row
        for row in rows
        if row["Bron"] == source
        and row["Bronlaag"] == layer
        and row["Bronwaarde"] == explicit
    )
    fallback = row.copy()
    fallback.update(
        {
            "Bronwaarde": "*",
            "LGB-code_binnendijks": "110",
            "LGB_beschrijving": "Vangnet",
        }
    )
    rows.insert(0, fallback)
    table = load_landuse_table(write_table(tmp_path, rows))
    values = [explicit.upper(), "unknown", "", "  ", None]
    data = gpd.GeoDataFrame(
        {field: values}, geometry=[box(i, 0, i + 1, 1) for i in range(5)], crs=28992
    )
    result = _assign_source_codes(
        data, table.source_values(source, layer), field=field, dike_area=None
    )
    assert result.index.tolist() == [0, 1]
    assert result["code"].tolist() == [int(row["LGB-code_binnendijks"]), 110]
    with pytest.raises(ValueError, match="Bronveld ontbreekt"):
        _assign_source_codes(
            data.drop(columns=field),
            table.source_values(source, layer),
            field=field,
            dike_area=None,
        )


def test_blank_field_all_objects(tmp_path):
    path = tmp_path / "bgt.gpkg"
    data = gpd.GeoDataFrame(
        {
            "bgt-status": ["bestaand", "bestaand"],
            "eindRegistratie": [None, None],
            "objectEindTijd": [None, None],
        },
        geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1)],
        crs=28992,
    )
    data.to_file(path, layer="bgt_waterdeel", driver="GPKG")
    result = prepare_bgt_layer(
        path,
        layer="bgt_waterdeel",
        mapping_layer="bgt_waterdeel",
        bounds=(-1, -1, 4, 2),
        dike_area=box(-1, -1, 4, 2),
    )
    assert result["code"].tolist() == [100, 100]


def test_blank_field_requires_wildcard(tmp_path, rows):
    row = next(row for row in rows if row["Bronlaag"] == "bgt_waterdeel")
    row["Bronwaarde"] = "water"
    with pytest.raises(ValueError, match="leeg Bronveld"):
        load_landuse_table(write_table(tmp_path, rows))


def test_wildcard_alone_does_not_disable_field_matching(tmp_path, rows):
    row = next(row for row in rows if row["Bronlaag"] == "bgt_wegdeel")
    row = {**row, "Bronwaarde": "*"}
    table = load_landuse_table(write_table(tmp_path, [row]))
    assert table.source_values("BGT", "bgt_wegdeel")["*"].field == "bgt-functie"


def test_mapping_id_is_not_a_function_lookup(tmp_path, rows):
    row = next(row for row in rows if row["Koppelmethode"] == "mapping")
    row["Koppel-ID"] = "my-row"
    table = load_landuse_table(write_table(tmp_path, rows))
    with pytest.raises(ValueError, match="ontbreekt"):
        table.by_id("my-row")


def test_palette_and_legends_are_order_independent(tmp_path, rows):
    # No +128 owner for 250: combine descriptions. Existing 182 retains its owner.
    rows[0]["LGB-code_buitendijks"] = "250"
    rows[1]["LGB-code_buitendijks"] = "250"
    expected_labels = None
    expected_colors = None
    for seed in range(3):
        random.Random(seed).shuffle(rows)
        table = load_landuse_table(write_table(tmp_path, rows))
        colors = build_colormap(table)
        style = write_qgis_style(tmp_path / "map.tif", table)
        labels = {
            int(entry.attrib["value"]): entry.attrib["label"]
            for entry in ET.parse(style).iter("paletteEntry")
        }
        if expected_labels is None:
            expected_labels, expected_colors = labels, colors
        assert labels == expected_labels
        assert colors == expected_colors
    assert (
        labels[250]
        == "250 — Woning met begane grond en eerste verdieping; Woning met enkel begane grond (buitendijks)"
    )
    assert labels[182] == "182 — Overig gras/natuur (geen schade) (buitendijks)"
    assert colors[50] == (125, 190, 90, 255)
