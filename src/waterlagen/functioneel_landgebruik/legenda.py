"""Display colors for the actual codes in the land-use CSV."""

import os
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from waterlagen.functioneel_landgebruik.landgebruikstabel import LanduseTable
from waterlagen.logger import get_logger

logger = get_logger(__name__)


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

    root = ET.Element("qgis", version="3.40", styleCategories="Symbology")
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
