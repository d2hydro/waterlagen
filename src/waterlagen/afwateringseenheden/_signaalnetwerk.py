"""Read only watercourses and culverts proven to participate in the connected network."""

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio
from rasterio.windows import from_bounds
from shapely.geometry import box

from waterlagen._crs import same_crs
from waterlagen._geopandas import read_file
from waterlagen.logger import get_logger

from .brandlagen import _rasterize_brand_shapes

logger = get_logger(__name__)


def _validate_network(features: gpd.GeoDataFrame, reference: gpd.GeoDataFrame) -> None:
    if features.crs is None or not same_crs(features.crs, reference.crs):
        raise ValueError("Signaalkaart: afwijkend CRS voor gebruikt watersysteem")
    if (
        features.geometry.isna().any()
        or features.is_empty.any()
        or (~features.is_valid).any()
    ):
        raise ValueError("Signaalkaart: ongeldige geometrie in gebruikt watersysteem")


def _connected_culverts(run_dir: Path, signals: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Require applied burn cells and connected waternet treatment, not just suitability."""
    empty = signals.iloc[:0][["geometry"]].copy()
    path = run_dir / "controle.gpkg"
    if not path.is_file() or "duikers_waternet" not in pyogrio.list_layers(path)[:, 0]:
        return empty
    controls = read_file(path, layer="duikers_waternet")
    _validate_network(controls, signals)
    if not {"behandeling", "bron_id", "broncode"}.issubset(controls.columns):
        logger.warning(
            "Geen objectkoppeling voor duikers; niet gebruikt als uitsluitingsgrond"
        )
        return empty
    controls = controls.loc[controls.behandeling.isin(["aanvoer", "primair_primair"])]
    if controls.empty or signals.empty:
        return empty
    positions = controls.sindex.query(
        signals.geometry, predicate="dwithin", distance=2.0
    )[1]
    controls = controls.iloc[np.unique(positions)]
    connected: set[str] = set()
    unconnected: set[str] = set()
    for audit_path in sorted(
        (run_dir / "berekening" / "tegels").glob("*/duiker_inbranding.json")
    ):
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        applied = {
            key
            for key, counts in audit.get("objects", {}).items()
            if counts.get("toegepast", 0) > 0
        }
        local = controls.loc[controls.bron_id.isin(applied)]
        if local.empty:
            continue
        recorded = audit.get("waternet", {}).get("path")
        if not recorded:
            continue
        raster_path = (
            run_dir / "berekening" / "waterlopen_duikers" / Path(recorded).name
        )
        if not raster_path.is_file():
            continue
        with rasterio.open(raster_path) as raster:
            if (
                raster.crs is None
                or not same_crs(raster.crs, signals.crs)
                or raster.count < 2
            ):
                raise ValueError("Signaalkaart: ongeldig waternetraster voor duikers")
            for row in local.itertuples():
                bounds = (
                    row.geometry.envelope.buffer(max(raster.res))
                    .intersection(box(*raster.bounds))
                    .bounds
                )
                if len(bounds) != 4 or not np.isfinite(bounds).all():
                    continue
                window = (
                    from_bounds(*bounds, raster.transform)
                    .round_offsets()
                    .round_lengths()
                )
                treatment, codes = raster.read([1, 2], window=window)
                if treatment.size == 0:
                    continue
                mask = _rasterize_brand_shapes(
                    [(row.geometry, 1)],
                    out_shape=treatment.shape,
                    transform=raster.window_transform(window),
                    dtype="uint8",
                ).astype(bool)
                own_cells = mask & (codes == row.broncode)
                if np.any(own_cells & (treatment == 2)):
                    connected.add(str(row.bron_id))
                if np.any(own_cells & (treatment == 3)):
                    unconnected.add(str(row.bron_id))
    accepted = connected - unconnected
    return controls.loc[controls.bron_id.isin(accepted), ["geometry"]].copy()


def read_used_network(
    run_dir: Path, primary: gpd.GeoDataFrame, signals: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Use published connected watercourses and culverts with connected applied cells."""
    frames = [primary[["geometry"]]]
    path = run_dir / "watersysteem.gpkg"
    layers = set(pyogrio.list_layers(path)[:, 0])
    for name in ("hydroobject_secundair", "hydroobject_tertiair"):
        if name not in layers:
            continue
        waterlines = read_file(path, layer=name)
        _validate_network(waterlines, signals)
        frames.append(waterlines[["geometry"]])
    culverts = _connected_culverts(run_dir, signals)
    frames.append(culverts)
    network = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=signals.crs)
    logger.info(
        "2-metercontrole: %s verbonden waterobjecten, waarvan %s duikers",
        len(network),
        len(culverts),
    )
    return network
