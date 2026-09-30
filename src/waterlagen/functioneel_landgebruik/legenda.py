"""Display colors for the actual codes in the land-use CSV."""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from osgeo import gdal

from waterlagen.functioneel_landgebruik.landgebruikstabel import LanduseTable
from waterlagen.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PaletteEntry:
    value: int
    label: str
    red: int
    green: int
    blue: int
    alpha: int


def _read_qgis_palette(style_path: Path) -> list[PaletteEntry]:
    """Read the exact-value classes already written to the QGIS style."""
    renderer = ET.parse(style_path).find(".//rasterrenderer")
    if renderer is None or renderer.get("type") != "paletted":
        raise ValueError(
            f"QGIS-stijl gebruikt geen palet met unieke waarden: {style_path}"
        )
    palette = renderer.find("colorPalette")
    if palette is None:
        raise ValueError(f"QGIS-stijl bevat geen kleurenpalet: {style_path}")

    entries = []
    seen = set()
    for item in palette.findall("paletteEntry"):
        value = int(item.attrib["value"])
        color = item.attrib["color"]
        if value in seen or len(color) != 7 or not color.startswith("#"):
            raise ValueError(f"Ongeldige of dubbele paletwaarde {value}: {style_path}")
        seen.add(value)
        entries.append(
            PaletteEntry(
                value=value,
                label=item.attrib["label"],
                red=int(color[1:3], 16),
                green=int(color[3:5], 16),
                blue=int(color[5:7], 16),
                alpha=int(item.attrib.get("alpha", "255")),
            )
        )
    if not entries:
        raise ValueError(f"QGIS-stijl bevat geen paletwaarden: {style_path}")
    return entries


def write_raster_attribute_table(raster_path: Path, style_path: Path) -> Path:
    """Write the QGIS palette as a portable GDAL RAT beside a finished COG.

    The RAT is stored in ``<raster>.aux.xml`` for GDAL versions used by QGIS
    3.30. Opening the COG read-only leaves its tiles and overviews untouched.
    """
    raster_path = Path(raster_path)
    entries = _read_qgis_palette(Path(style_path))
    rat = gdal.RasterAttributeTable()
    columns = (
        ("Value", gdal.GFT_Integer, gdal.GFU_MinMax),
        ("Name", gdal.GFT_String, gdal.GFU_Name),
        ("Red", gdal.GFT_Integer, gdal.GFU_Red),
        ("Green", gdal.GFT_Integer, gdal.GFU_Green),
        ("Blue", gdal.GFT_Integer, gdal.GFU_Blue),
        ("Alpha", gdal.GFT_Integer, gdal.GFU_Alpha),
    )
    for name, field_type, usage in columns:
        rat.CreateColumn(name, field_type, usage)
    rat.SetRowCount(len(entries))
    for row, entry in enumerate(entries):
        rat.SetValueAsInt(row, 0, entry.value)
        rat.SetValueAsString(row, 1, entry.label)
        for column, channel in enumerate(
            (entry.red, entry.green, entry.blue, entry.alpha), start=2
        ):
            rat.SetValueAsInt(row, column, channel)

    sidecar = raster_path.with_name(f"{raster_path.name}.aux.xml")
    with gdal.config_option("GTIFF_WRITE_RAT_TO_PAM", "YES"):
        dataset = gdal.Open(str(raster_path), gdal.GA_ReadOnly)
        if dataset is None:
            raise ValueError(f"Raster kan niet worden geopend voor RAT: {raster_path}")
        try:
            if dataset.GetRasterBand(1).SetDefaultRAT(rat) != gdal.CE_None:
                raise RuntimeError(f"RAT schrijven mislukt: {raster_path}")
        finally:
            dataset = None

    if not sidecar.is_file():
        raise RuntimeError(f"RAT-bijlage ontbreekt: {sidecar}")
    dataset = gdal.Open(str(raster_path), gdal.GA_ReadOnly)
    try:
        saved = dataset.GetRasterBand(1).GetDefaultRAT()
        if saved is None or saved.GetRowCount() != len(entries):
            raise RuntimeError(f"RAT is niet volledig opgeslagen: {sidecar}")
        for row, entry in enumerate(entries):
            values = tuple(saved.GetValueAsInt(row, column) for column in range(2, 6))
            if (
                saved.GetValueAsInt(row, 0) != entry.value
                or saved.GetValueAsString(row, 1) != entry.label
                or values != (entry.red, entry.green, entry.blue, entry.alpha)
            ):
                raise RuntimeError(f"RAT wijkt af van de QGIS-legenda: {sidecar}")
    finally:
        saved = None
        dataset = None
    logger.info("Rasterattribuuttabel geschreven: %s", sidecar)
    return sidecar


def build_colormap(table: LanduseTable) -> dict[int, tuple[int, int, int, int]]:
    """Return RGBA colors for CSV codes, with transparent NoData.

    Parameters
    ----------
    table : LanduseTable
        Validated mappings used to classify the raster.

    Returns
    -------
    dict
        Both location codes of a class share a display color. Colors do not
        determine classification or overlap priority.
    """
    colors = {0: (0, 0, 0, 0)}
    # Fixed source precedence preserves the bundled palette, regardless of CSV
    # order: water, buildings, BRP, TOP10NL, roads, other terrain/pumps.
    candidates = {}
    for row in table.rows:
        if row.layer == "bgt_waterdeel":
            priority = 0
            color = (0, 130, 255, 255)
        elif row.source == "BAG" or "+ BAG" in row.source:
            priority = 1
            color = (235, 180, 65, 255)
        elif row.source == "BRP":
            priority = 2
            color = (125, 190, 90, 255)
        elif row.source == "TOP10NL":
            priority = 3
            color = (185, 105, 185, 255)
        elif row.layer in {"bgt_wegdeel", "bgt_ondersteunendwegdeel"}:
            priority = 4
            color = (210, 85, 70, 255)
        else:
            priority = 5
            color = (100, 155, 90, 255)
        for code in (row.inside, row.outside):
            candidate = (priority, color)
            if code not in candidates or candidate < candidates[code]:
                candidates[code] = candidate
    colors.update({code: candidate[1] for code, candidate in candidates.items()})
    return colors


def write_qgis_style(raster_path: Path, table: LanduseTable) -> Path:
    """Write a QGIS palette with category labels beside an existing raster.

    Parameters
    ----------
    raster_path : pathlib.Path
        Raster whose same-stem ``.qml`` style is created or replaced.
        The raster itself is not modified.
    table : LanduseTable
        The mapping table used when producing this raster.

    Returns
    -------
    pathlib.Path
        Style file, written atomically. Keep it beside the raster when copying.
    """
    labels = {0: "0 — NoData / niet ingedeeld"}
    for row in table.rows:
        labels[row.inside] = f"{row.inside} — {row.description} (binnendijks)"
    for code in sorted({row.outside for row in table.rows}):
        rows = [row for row in table.rows if row.outside == code]
        preferred = [row for row in rows if row.outside == row.inside + 128]
        descriptions = sorted({row.description for row in preferred or rows})
        labels[code] = f"{code} — {'; '.join(descriptions)} (buitendijks)"

    root = ET.Element("qgis", version="3.30", styleCategories="Symbology")
    pipe = ET.SubElement(root, "pipe")
    renderer = ET.SubElement(
        pipe, "rasterrenderer", type="paletted", band="1", opacity="1", alphaBand="-1"
    )
    palette = ET.SubElement(renderer, "colorPalette")
    colors = build_colormap(table)
    for code, label in sorted(labels.items()):
        red, green, blue, alpha = colors[code]
        ET.SubElement(
            palette,
            "paletteEntry",
            value=str(code),
            label=label,
            color=f"#{red:02x}{green:02x}{blue:02x}",
            alpha=str(alpha),
        )
    ET.indent(root)
    target = Path(raster_path).with_suffix(".qml")
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            ET.ElementTree(root).write(stream, encoding="utf-8", xml_declaration=True)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    logger.info("QGIS-legenda geschreven: %s", target)
    return target
