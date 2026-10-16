"""Select source networks independently of drainage-target participation."""

from dataclasses import dataclass
from pathlib import Path
import re

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry.base import BaseGeometry

from waterlagen import _geopandas as wgpd
from waterlagen.logger import get_logger
from waterlagen.settings import settings

from .objects import (
    CATEGORIE_OPPERVLAKTEWATER_COLUMN,
    read_hydroobjecten,
    read_puntobjecten,
)

logger = get_logger(__name__)
SOURCE_POLICY = "replace_authority_exclude_gkw80_missing_category_control_v2"
CONNECTION_POLICY = "all_selected_full_lines_components_v1"


@dataclass(frozen=True)
class WatersysteemSources:
    """Full burn context and separate drainage-target selections.

    Attributes
    ----------
    primary, secondary : geopandas.GeoDataFrame
        Full selected primary and secondary lines across all authorities.
        Secondary connectivity is classified jointly when writing the network.
    targets : geopandas.GeoDataFrame
        Primary lines of participating authorities, before segmentation.
    points : geopandas.GeoDataFrame
        Gemaal and stuw objects of participating authorities.
    missing_category : geopandas.GeoDataFrame, optional
        GKW lines without a category, excluded from burning and targets and
        retained with provenance for inspection.
    """

    primary: gpd.GeoDataFrame
    secondary: gpd.GeoDataFrame
    targets: gpd.GeoDataFrame
    points: gpd.GeoDataFrame
    missing_category: gpd.GeoDataFrame | None = None


def validate_authority_options(
    waterbeheercode: str | None, overige_waterschappen: bool, eigen_hydamo: Path | None
) -> None:
    """Reject authority-specific options without an authority selection."""
    if waterbeheercode is None and (overige_waterschappen or eigen_hydamo is not None):
        raise ValueError(
            "overige_waterschappen en eigen_hydamo vereisen een waterbeheercode"
        )
    if waterbeheercode == "80":
        raise ValueError(
            "Code 80 is Rijkswaterstaat; kies een gebied zonder waterschapscode"
        )


def _check_identifiers(
    features: gpd.GeoDataFrame, label: str, code: str | None = None
) -> None:
    identifiers = features.get("nen3610id")
    if identifiers is None:
        if features.empty:
            return
        raise ValueError(f"{label}: missing nen3610id")
    codes = identifiers.astype("string").str.extract(
        r"^NL\.WBHCODE\.([0-9]+)\..+$", expand=False
    )
    invalid = codes.isna()
    if code is not None:
        invalid = invalid | codes.ne(code).fillna(True)
    if invalid.any():
        fids = (
            features["bron_fid"]
            if "bron_fid" in features
            else features.index.to_series()
        )
        raise ValueError(
            f"{label}: missing, invalid or unexpected nen3610id at FIDs {list(fids[invalid])}"
        )


def _validate_own_source(path: Path, code: str) -> None:
    """Check the entire delivery, including objects outside the selected context."""
    logger.info("Validating own HyDAMO delivery %s for authority %s", path, code)
    available = set(pyogrio.list_layers(path)[:, 0])
    missing = {"hydroobject", "gemaal", "stuw"} - available
    if missing:
        raise ValueError(
            f"{path}: missing required layers: {', '.join(sorted(missing))}"
        )
    for layer in ("hydroobject", "gemaal", "stuw"):
        features = wgpd.read_file(path, layer=layer, fid_as_index=True)
        if features.crs is None:
            raise ValueError(f"{path} / {layer}: missing CRS")
        _check_identifiers(features, f"{path} / {layer}", code)
        if layer == "hydroobject":
            _normalize_categories(features, str(path))


def _normalize_categories(
    features: gpd.GeoDataFrame, label: str, *, allow_missing: bool = False
) -> gpd.GeoDataFrame:
    """Normalize explicit source column aliases; never infer unknown categories."""
    result = features.copy()
    canonical = CATEGORIE_OPPERVLAKTEWATER_COLUMN
    alias = "categorieoppervlaktewater"
    if canonical not in result and alias not in result:
        raise ValueError(f"{label}: missing surface-water category")
    if canonical in result and alias in result:
        conflict = (
            result[canonical].notna()
            & result[alias].notna()
            & result[canonical].ne(result[alias])
        )
        if conflict.any():
            raise ValueError(f"{label}: conflicting category columns")
        result[canonical] = result[canonical].fillna(result[alias])
    elif canonical not in result:
        result[canonical] = result[alias]
    accepted = result[canonical].isin(["primair", "secundair", "tertiair", "overig"])
    if allow_missing:
        accepted = accepted | result[canonical].isna()
    if not accepted.all():
        raise ValueError(f"{label}: unknown or missing surface-water category")
    return result


def _source_ids(features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    result = features.copy()
    if result.empty:
        return result
    # Include the path, layer and original FID, even when globalids are reused.
    result["bron_id"] = [
        f"{row.bronbestand}|{row.bronlaag}|{row.bron_fid}|{row.bron_id}"
        for row in result.itertuples()
    ]
    return result


def read_watersysteem_sources(
    hydamo_path: Path,
    rijkswateren_path: Path,
    *,
    spatial_selection: BaseGeometry,
    waterbeheercode: str | None = None,
    overige_waterschappen: bool = False,
    eigen_hydamo: Path | None = None,
) -> WatersysteemSources:
    """Read full source geometries and select participating drainage targets.

    Parameters
    ----------
    hydamo_path, rijkswateren_path : pathlib.Path
        Local GKW and published RWS sources. GKW code 80 lines are excluded.
    spatial_selection : shapely.geometry.base.BaseGeometry
        Complete calculation grids and buffers in ``settings.crs``; no clipping.
    waterbeheercode : str, optional
        Selected authority. Without a code, all authorities including RWS supply
        primary targets. With a code, RWS supplies only burn context.
    overige_waterschappen : bool, optional
        Include other water authorities as targets, default False. Requires a code.
    eigen_hydamo : pathlib.Path, optional
        Completely replaces the selected authority's hydroobject, gemaal and stuw
        layers. All identifiers are checked before spatial selection; no fallback.

    Returns
    -------
    WatersysteemSources
        Primary and secondary burn context, primary targets and participating
        points, with original identifiers and file/layer/FID provenance.
        GKW lines without a category are warned about and retained separately;
        ``overig`` and ``tertiair`` supply neither burning nor targets.

    Raises
    ------
    ValueError
        Invalid identifiers, categories, missing CRS or own-source layers.
    """
    validate_authority_options(waterbeheercode, overige_waterschappen, eigen_hydamo)
    if waterbeheercode is not None and not re.fullmatch(r"[0-9]+", waterbeheercode):
        raise ValueError("waterbeheercode must contain digits")
    if eigen_hydamo is not None:
        _validate_own_source(eigen_hydamo, waterbeheercode)
    hydro = read_hydroobjecten(hydamo_path, spatial_selection=spatial_selection)
    points = read_puntobjecten(hydamo_path, spatial_selection=spatial_selection)
    hydro = hydro.loc[hydro.waterbeheercode.ne("80")].copy()
    if eigen_hydamo is not None:
        hydro = hydro.loc[hydro.waterbeheercode.ne(waterbeheercode)].copy()
        points = points.loc[points.waterbeheercode.ne(waterbeheercode)].copy()
        own_hydro = read_hydroobjecten(
            eigen_hydamo, spatial_selection=spatial_selection
        )
        own_points = read_puntobjecten(
            eigen_hydamo, spatial_selection=spatial_selection
        )
        hydro = pd.concat([hydro, own_hydro], ignore_index=True)
        points = pd.concat([points, own_points], ignore_index=True)
    hydro = _normalize_categories(hydro, str(hydamo_path), allow_missing=True)
    rws = read_hydroobjecten(rijkswateren_path, spatial_selection=spatial_selection)
    _check_identifiers(rws, str(rijkswateren_path), "80")
    rws = _normalize_categories(rws, str(rijkswateren_path))
    hydro = gpd.GeoDataFrame(
        pd.concat([hydro, rws], ignore_index=True), crs=settings.crs
    )
    _check_identifiers(hydro, "Selected hydroobjecten")
    _check_identifiers(points, "Selected point objects")
    hydro = _source_ids(hydro)
    points = _source_ids(points)
    missing_category = hydro.loc[hydro[CATEGORIE_OPPERVLAKTEWATER_COLUMN].isna()].copy()
    missing_category["uitsluitreden"] = "categorie ontbreekt"
    if not missing_category.empty:
        logger.warning(
            "Excluded %s GKW hydroobjects without a category from burning and targets; "
            "retained in hydroobject_zonder_categorie with file/layer/FID provenance",
            len(missing_category),
        )
    primary = hydro.loc[hydro[CATEGORIE_OPPERVLAKTEWATER_COLUMN].eq("primair")].copy()
    secondary = hydro.loc[
        hydro[CATEGORIE_OPPERVLAKTEWATER_COLUMN].eq("secundair")
    ].copy()
    primary["brandcategorie"] = "primair"
    secondary["brandcategorie"] = "secundair"
    targets = primary.copy()
    if waterbeheercode is not None:
        if overige_waterschappen:
            targets = targets.loc[targets.waterbeheercode.ne("80")].copy()
            points = points.loc[points.waterbeheercode.ne("80")].copy()
        else:
            targets = targets.loc[targets.waterbeheercode.eq(waterbeheercode)].copy()
            points = points.loc[points.waterbeheercode.eq(waterbeheercode)].copy()
    logger.info(
        "Selected %s primary burn lines, %s secondary lines, %s targets and %s points",
        len(primary),
        len(secondary),
        len(targets),
        len(points),
    )
    return WatersysteemSources(primary, secondary, targets, points, missing_category)
