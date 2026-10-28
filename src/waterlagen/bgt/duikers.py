"""Select current BGT culverts without discarding line or polygon geometries."""

from pathlib import Path

import geopandas as gpd
import pyogrio
from shapely.geometry.base import BaseGeometry

from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._geopandas import read_file
from waterlagen.logger import get_logger
from waterlagen.settings import settings

logger = get_logger(__name__)


def prepare_bgt_culverts(source: Path, target: Path, selection: BaseGeometry) -> Path:
    """Select current culverts, preserving complete supported geometries.

    Parameters
    ----------
    source : Path
        GeoPackage with ``bgt_kunstwerkdeel`` and a known CRS. Use the general
        BGT conversion to retain both lines and polygons; surface-only input
        cannot recover discarded lines.
    target : Path
        Output GeoPackage, atomically replaced after validation.
    selection : BaseGeometry
        Required calculation coverage in ``settings.crs``.

    Returns
    -------
    Path
        GeoPackage with layer ``bgt_duiker`` and original FIDs in ``bron_fid``.
    """
    info = pyogrio.read_info(source, layer="bgt_kunstwerkdeel")
    if not info["crs"]:
        raise ValueError("BGT-kunstwerkdelen hebben geen CRS")
    fields = set(info["fields"])
    if not {"plus-type", "bgt-status"}.issubset(fields):
        raise ValueError("BGT-kunstwerkdelen vereisen plus-type en bgt-status")
    filters = ["\"plus-type\" = 'duiker'", "\"bgt-status\" = 'bestaand'"]
    for field in ("eindRegistratie", "objectEindTijd"):
        if field in fields:
            filters.append(f'"{field}" IS NULL')
    source_selection = gpd.GeoSeries([selection], crs=settings.crs).to_crs(info["crs"])
    features = read_file(
        source,
        layer="bgt_kunstwerkdeel",
        bbox=tuple(source_selection.total_bounds),
        where=" AND ".join(filters),
        fid_as_index=True,
    ).to_crs(settings.crs)
    valid = (
        features.geometry.notna()
        & features.geometry.is_valid
        & ~features.geometry.is_empty
    )
    supported = features.geom_type.isin(
        ["LineString", "MultiLineString", "Polygon", "MultiPolygon"]
    )
    if not (valid & supported).all():
        raise ValueError(
            "BGT-duikers bevatten ongeldige of niet-ondersteunde geometrieën"
        )
    features = features.loc[features.intersects(selection)].copy()
    features["bron_fid"] = features.index
    logger.info("BGT-duikers voorbereiden: %s (%s objecten)", target, len(features))
    write_geopackage_layer_atomically(features, target, layer_name="bgt_duiker")
    return target
