"""Prepare current source geometries and assign the CSV's land-use codes."""

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry.base import BaseGeometry

from waterlagen import _geopandas as wgpd
from waterlagen._crs import same_crs
from waterlagen.functioneel_landgebruik.bag_gebruiksfunctie import (
    determine_bag_functions,
)
from waterlagen.functioneel_landgebruik.bag_landgebruik import determine_bag_classes
from waterlagen.functioneel_landgebruik.bag_panden_en_verblijfsobjecten import (
    BagSourceData,
    read_bag_source_data,
)
from waterlagen.functioneel_landgebruik.bag_verdiepingen import determine_bag_floors
from waterlagen.functioneel_landgebruik.gemalen import (
    classify_pumping_stations,
)
from waterlagen.functioneel_landgebruik.kassen_rwzi_drinkwater import (
    SpecialBuildingSources,
    apply_special_building_classes,
)
from waterlagen.functioneel_landgebruik.landgebruikstabel import (
    LanduseMapping,
    LanduseTable,
    load_landuse_table,
)
from waterlagen.functioneel_landgebruik.nodata_verklaren import LanduseDiagnostics
from waterlagen.logger import get_logger
from waterlagen.settings import settings

logger = get_logger(__name__)


def _mapping_field(mappings: dict[str, LanduseMapping]) -> str:
    """Require one CSV source field for a source layer."""
    fields = {row.field for row in mappings.values()}
    if len(fields) != 1:
        raise ValueError("Meerdere bronvelden voor dezelfde bronlaag in de CSV")
    return fields.pop()


def _assign_source_codes(
    data: gpd.GeoDataFrame,
    mappings: dict[str, LanduseMapping],
    *,
    field: str | None,
    dike_area: BaseGeometry | None,
    numeric_values: bool = False,
    source_layer: str = "onbekend",
    diagnostics: LanduseDiagnostics | None = None,
    source: str = "",
    source_path: Path | None = None,
) -> gpd.GeoDataFrame:
    """Match complete values and choose the CSV code for the dike location."""
    if data.crs is None or not same_crs(data.crs, settings.crs):
        raise ValueError(
            f"CRS van {source_layer} ({data.crs}) verschilt van {settings.crs}."
        )
    result = data.dropna(subset=["geometry"]).copy()
    if field is None:
        keys = pd.Series("*", index=result.index)
    elif field not in result.columns:
        raise ValueError(f"Bronveld ontbreekt: {field}")
    elif numeric_values:
        numbers = pd.to_numeric(result[field], errors="coerce")
        valid = numbers.notna() & (numbers > 0) & (numbers % 1 == 0)
        keys = numbers.where(valid).astype("Int64").astype("string")
    else:
        keys = result[field].astype("string").str.strip().str.casefold()

    matched = keys.map(mappings)
    fallback = mappings.get("*")
    if fallback is not None and field is not None:
        remaining = matched.isna() & keys.notna()
        if remaining.any():
            logger.warning(
                "%s bronwaarden gebruiken CSV-vangnet %s: %s",
                int(remaining.sum()),
                fallback.ids[0],
                sorted(keys[remaining].unique())[:10],
            )
            matched.loc[remaining] = pd.Series(
                [fallback] * int(remaining.sum()), index=matched.index[remaining]
            )
    unknown = matched.isna()
    if unknown.any():
        if diagnostics is not None and source_path is not None:
            excluded = result.loc[unknown]
            reasons = pd.Series(
                "Geen koppeling voor deze bronwaarde in de CSV.", index=excluded.index
            )
            if field is not None:
                values = excluded[field].astype("string")
                missing = values.isna() | values.str.strip().eq("")
                if numeric_values:
                    reasons.loc[keys.loc[unknown].isna()] = (
                        "Gewascode is geen positief geheel getal."
                    )
                reasons.loc[missing] = "Bronwaarde ontbreekt."
            diagnostics.add(
                excluded,
                source=source,
                layer=source_layer,
                source_path=source_path,
                stage="CSV-koppeling",
                reason=reasons,
                value_column=field,
            )
        logger.warning(
            "CSV-indeling: laag=%s; veld=%s; %s van %s objecten zonder koppeling. "
            "Geen klasse uit deze bronlaag toegekend. Aantallen per bronwaarde: %s",
            source_layer,
            field,
            int(unknown.sum()),
            len(data),
            keys[unknown]
            .astype("string")
            .fillna("<ontbreekt>")
            .value_counts()
            .to_dict(),
        )
    result = result.loc[~unknown].copy()
    matched = matched.loc[~unknown]
    inside = pd.Series(True, index=result.index)
    if dike_area is not None:
        inside = result.geometry.representative_point().covered_by(dike_area)
    inside_codes = matched.map(lambda row: row.inside)
    outside_codes = matched.map(lambda row: row.outside)
    result["code"] = inside_codes.where(inside, outside_codes).astype("uint8")
    return result[["geometry", "code"]]


def prepare_functionele_gebieden(
    top10nl_gpkg: Path,
    *,
    layer: str,
    bounds: tuple[float, float, float, float],
    dike_area: BaseGeometry,
    table: LanduseTable | None = None,
    diagnostics: LanduseDiagnostics | None = None,
) -> gpd.GeoDataFrame:
    """Map complete TOP10NL functional-area values to CSV codes.

    Parameters
    ----------
    top10nl_gpkg : pathlib.Path
        TOP10NL GeoPackage.
    layer : str
        Functional-area layer to read (vlak or multivlak).
    bounds : tuple of float
        Read bounds in the source CRS.
    dike_area : BaseGeometry
        Dike-ring union in the same CRS.
    table : LanduseTable, optional
        Defaults to the packaged CSV.
    diagnostics : LanduseDiagnostics, optional
        Bewaar objecten zonder CSV-koppeling voor de QGIS-controle.

    Returns
    -------
    geopandas.GeoDataFrame
        Geometry and code. Unlisted values are logged and excluded.
    """
    table = table or load_landuse_table()
    mapping_layer = (
        "top10nl_functioneel_gebied_multivlak"
        if layer.endswith("multivlak")
        else "top10nl_functioneel_gebied_vlak"
    )
    mappings = table.source_values("TOP10NL", mapping_layer)
    field = _mapping_field(mappings)
    data = wgpd.read_file(
        top10nl_gpkg,
        layer=layer,
        bbox=bounds,
        columns=[field, "geometry"],
        fid_as_index=diagnostics is not None,
    )
    logger.info("Read %s TOP10NL functional areas from layer %s", len(data), layer)
    return _assign_source_codes(
        data,
        mappings,
        field=field,
        dike_area=dike_area,
        source_layer=layer,
        diagnostics=diagnostics,
        source="TOP10NL",
        source_path=top10nl_gpkg,
    )


def prepare_brp(
    brp_gpkg: Path,
    *,
    layer: str,
    bounds: tuple[float, float, float, float],
    dike_area: BaseGeometry,
    table: LanduseTable | None = None,
    diagnostics: LanduseDiagnostics | None = None,
) -> gpd.GeoDataFrame:
    """Classify BRP by numeric crop code, including mapped landscape elements.

    Parameters
    ----------
    brp_gpkg : pathlib.Path
        BRP GeoPackage.
    layer : str
        Crop-parcel layer.
    bounds : tuple of float
        Read bounds in the source CRS.
    dike_area : BaseGeometry
        Dike-ring union in the same CRS.
    table : LanduseTable, optional
        Defaults to the packaged CSV. An explicit fallback row may map unknown
        positive crop codes; missing/invalid crop codes do not use it.
    diagnostics : LanduseDiagnostics, optional
        Bewaar objecten zonder CSV-koppeling voor de QGIS-controle.

    Returns
    -------
    geopandas.GeoDataFrame
        Geometry and code. Crop values without a mapping are logged and excluded.
    """
    table = table or load_landuse_table()
    mappings = table.source_values("BRP", "brp_gewas")
    field = _mapping_field(mappings)
    data = wgpd.read_file(
        brp_gpkg,
        layer=layer,
        bbox=bounds,
        columns=[field, "geometry"],
        fid_as_index=diagnostics is not None,
    )
    return _assign_source_codes(
        data,
        mappings,
        field=field,
        dike_area=dike_area,
        numeric_values=True,
        source_layer=layer,
        diagnostics=diagnostics,
        source="BRP",
        source_path=brp_gpkg,
    )


def _filter_actuele_bgt(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep existing registrations with neither registration nor object ended."""
    required = {"bgt-status", "eindRegistratie", "objectEindTijd"}
    missing = required.difference(gdf.columns)
    if missing:
        raise ValueError(
            "BGT-actualiteitsfilter mist kolommen: "
            + ", ".join(sorted(missing))
            + ". Maak de BGT-GeoPackage opnieuw met deze bronvelden."
        )
    # Historische registraties kunnen nog de status 'bestaand' hebben.
    return gdf[
        (gdf["bgt-status"] == "bestaand")
        & gdf["eindRegistratie"].isna()
        & gdf["objectEindTijd"].isna()
    ].copy()


def prepare_bgt_layer(
    bgt_gpkg: Path,
    *,
    layer: str,
    mapping_layer: str,
    bounds: tuple[float, float, float, float],
    dike_area: BaseGeometry | None,
    table: LanduseTable | None = None,
    diagnostics: LanduseDiagnostics | None = None,
) -> gpd.GeoDataFrame:
    """Filter current BGT objects, then assign exact CSV source-value mappings.

    Parameters
    ----------
    bgt_gpkg : pathlib.Path
        BGT GeoPackage including registration/object end fields.
    layer : str
        Actual source layer name.
    mapping_layer : str
        Corresponding BGT layer name in the CSV, without .gml.
    bounds : tuple of float
        Read bounds in the source CRS.
    dike_area : BaseGeometry or None
        Dike-ring union. None selects inside codes for standalone use only.
    table : LanduseTable, optional
        Defaults to the packaged CSV.
    diagnostics : LanduseDiagnostics, optional
        Bewaar uitgesloten historie en objecten zonder CSV-koppeling.

    Returns
    -------
    geopandas.GeoDataFrame
        Geometry and uint8 code. Historical objects are excluded.
    """
    table = table or load_landuse_table()
    mappings = table.source_values("BGT", mapping_layer)
    field = None if set(mappings) == {"*"} else _mapping_field(mappings)
    columns = ["bgt-status", "eindRegistratie", "objectEindTijd", "geometry"]
    if field is not None:
        columns.append(field)
    data = wgpd.read_file(
        bgt_gpkg,
        layer=layer,
        bbox=bounds,
        columns=columns,
        fid_as_index=diagnostics is not None,
    )
    current = _filter_actuele_bgt(data)
    if diagnostics is not None:
        excluded = data.loc[~data.index.isin(current.index)]
        reasons = pd.Series("Status is niet bestaand.", index=excluded.index)
        registration_ended = excluded["eindRegistratie"].notna()
        object_ended = excluded["objectEindTijd"].notna()
        reasons.loc[registration_ended] = (
            "Historische registratie: eindRegistratie is gevuld."
        )
        reasons.loc[object_ended] = "Beëindigd object: objectEindTijd is gevuld."
        reasons.loc[registration_ended & object_ended] = (
            "Registratie en object beëindigd: beide einddatumvelden zijn gevuld."
        )
        details = (
            "status="
            + excluded["bgt-status"].astype("string").fillna("leeg")
            + "; eindRegistratie="
            + excluded["eindRegistratie"].astype("string").fillna("leeg")
            + "; objectEindTijd="
            + excluded["objectEindTijd"].astype("string").fillna("leeg")
        )
        diagnostics.add(
            excluded,
            source="BGT",
            layer=layer,
            source_path=bgt_gpkg,
            stage="Actualiteitsfilter",
            reason=reasons,
            value_column=field,
            details=details,
        )
    return _assign_source_codes(
        current,
        mappings,
        field=field,
        dike_area=dike_area,
        source_layer=layer,
        diagnostics=diagnostics,
        source="BGT",
        source_path=bgt_gpkg,
    )


def prepare_water(
    bgt_gpkg: Path,
    *,
    layer: str,
    bounds: tuple[float, float, float, float],
    dike_area: BaseGeometry | None = None,
    table: LanduseTable | None = None,
    diagnostics: LanduseDiagnostics | None = None,
) -> gpd.GeoDataFrame:
    """Prepare current water objects using the water row in the CSV.

    Parameters
    ----------
    bgt_gpkg : pathlib.Path
        BGT GeoPackage.
    layer : str
        Water layer name.
    bounds : tuple of float
        Read bounds in the source CRS.
    dike_area : BaseGeometry, optional
        Dike-ring union. Omitted for compatibility with standalone calls,
        which then use the inside code. Production always provides it.
    table : LanduseTable, optional
        Defaults to the packaged CSV.
    diagnostics : LanduseDiagnostics, optional
        Bewaar uitgesloten waterobjecten voor de QGIS-controle.

    Returns
    -------
    geopandas.GeoDataFrame
        Current water geometries and their CSV code.
    """
    return prepare_bgt_layer(
        bgt_gpkg,
        layer=layer,
        mapping_layer="bgt_waterdeel",
        bounds=bounds,
        dike_area=dike_area,
        table=table,
        diagnostics=diagnostics,
    )


def prepare_wegen(
    bgt_gpkg: Path,
    *,
    layer: str,
    bounds: tuple[float, float, float, float],
    dike_area: BaseGeometry,
    table: LanduseTable | None = None,
    diagnostics: LanduseDiagnostics | None = None,
) -> gpd.GeoDataFrame:
    """Prepare current roads by their full BGT function value.

    Parameters
    ----------
    bgt_gpkg : pathlib.Path
        BGT GeoPackage.
    layer : str
        Road layer name.
    bounds : tuple of float
        Read bounds in the source CRS.
    dike_area : BaseGeometry
        Dike-ring union in the same CRS.
    table : LanduseTable, optional
        Defaults to the packaged CSV.
    diagnostics : LanduseDiagnostics, optional
        Bewaar uitgesloten wegen voor de QGIS-controle.

    Returns
    -------
    geopandas.GeoDataFrame
        Current classified road geometries and their CSV codes.
    """
    return prepare_bgt_layer(
        bgt_gpkg,
        layer=layer,
        mapping_layer="bgt_wegdeel",
        bounds=bounds,
        dike_area=dike_area,
        table=table,
        diagnostics=diagnostics,
    )


def select_bag_panden(
    panden: gpd.GeoDataFrame, *, status_col: str = "status"
) -> gpd.GeoDataFrame:
    """Select panden by status only, preserving all source columns.

    Parameters
    ----------
    panden : geopandas.GeoDataFrame
        Original BAG pand records. This input is not modified.
    status_col : str, optional
        Pand status column. A missing column raises ValueError.

    Returns
    -------
    geopandas.GeoDataFrame
        Panden with status Bouw gestart, Pand in gebruik or Verbouwing pand,
        per the note of 17 September 2025, page 4. Missing/other statuses are
        excluded. Case and surrounding whitespace are ignored for selection;
        the original status value is preserved. No function is selected.
    """
    if status_col not in panden.columns:
        raise ValueError(f"BAG-pandstatus ontbreekt: kolom {status_col}")
    status = panden[status_col].fillna("").astype(str).str.strip().str.lower()
    return panden[
        status.isin(["bouw gestart", "pand in gebruik", "verbouwing pand"])
    ].copy()


def classify_bag_panden(
    source: BagSourceData,
    *,
    through_step: int = 5,
    table: LanduseTable | None = None,
    special_sources: SpecialBuildingSources | None = None,
) -> gpd.GeoDataFrame:
    """Run the same BAG decisions for inspection and raster production.

    Parameters
    ----------
    source : BagSourceData
        Complete panden and linked VBOs read in step 1.
    through_step : int, optional
        Stop after status (2), function (3), floors (4), CSV class (5), or
        special buildings (6). Source records are not modified.
    table : LanduseTable, optional
        CSV codes used from step 5 onwards.
    special_sources : SpecialBuildingSources, optional
        Required for step 6. Pumping stations are linked afterwards.

    Returns
    -------
    geopandas.GeoDataFrame
        Status-selected panden with decisions through the requested step.
        Excluded panden are left out; the control script keeps them separately.
        No inside/outside location or raster code is assigned here.
    """
    if through_step not in (2, 3, 4, 5, 6):
        raise ValueError("Kies een BAG-stap van 2 tot en met 6.")
    if through_step == 6 and special_sources is None:
        raise ValueError("Stap 6 vereist TOP10NL als aanvullende bron.")

    # Deze volgorde is op één plek vastgelegd voor controle en productie.
    panden = select_bag_panden(source.panden)  # 2. Toegestane pandstatussen.
    if through_step >= 3:
        panden = determine_bag_functions(panden, source.verblijfsobjecten)
    if through_step >= 4:
        panden = determine_bag_floors(panden, source.verblijfsobjecten)
    if through_step >= 5:
        panden = determine_bag_classes(panden, table=table)
    if through_step == 6:
        panden = apply_special_building_classes(panden, special_sources, table=table)
    return panden


def prepare_bag(
    bag_gpkg: Path,
    *,
    pand_layer: str,
    verblijfsobject_layer: str,
    bounds: tuple[float, float, float, float],
    dike_area: BaseGeometry,
    include_details: bool = False,
    table: LanduseTable | None = None,
    special_sources: SpecialBuildingSources | None = None,
    diagnostics: LanduseDiagnostics | None = None,
) -> gpd.GeoDataFrame:
    """Prepare BAG using the same five steps as the control workflow.

    Parameters
    ----------
    bag_gpkg : pathlib.Path
        BAG Light GeoPackage.
    pand_layer, verblijfsobject_layer : str
        Source layer names.
    bounds : tuple of float
        Pand selection in EPSG:28992. Linked VBOs are also read outside bounds;
        pand geometries are not clipped before calculating their area.
    dike_area : shapely.geometry.base.BaseGeometry
        Dike-ring geometry in EPSG:28992. A representative point determines
        the inside/outside code for the entire pand.
    include_details : bool, optional
        Keep source and decision columns. Excluded statuses remain excluded.

    table : LanduseTable, optional
        CSV mappings shared with the other source preparations.
    special_sources : SpecialBuildingSources, optional
        Add step 6 (greenhouses and configured production sites). Omitted for
        standalone step-5 calls; the raster workflow supplies TOP10NL by default.
    diagnostics : LanduseDiagnostics, optional
        Bewaar afgewezen pandstatussen. Open klassen worden in de rasterbouw
        pas na de bijzondere gebouwen en gemaalkoppeling verzameld.

    Returns
    -------
    geopandas.GeoDataFrame
        Geometry and uint8 code, optionally with decision columns.
        Codes follow the September 2025 note. Unresolved classes get code 0
        (NoData), masking lower-priority land use under those buildings.
        They remain distinguishable in the details through klasse_status.
    """
    logger.info("Preparing BAG panden and linked verblijfsobjecten in %s", bounds)
    # 1. Read complete source objects, including VBOs outside the tile.
    source = read_bag_source_data(
        bag_gpkg,
        pand_layer=pand_layer,
        verblijfsobject_layer=verblijfsobject_layer,
        bounds=bounds,
    )
    # 2-6. Dezelfde stappen als in het controlescript, inclusief open keuzes.
    classes = classify_bag_panden(
        source,
        through_step=6 if special_sources is not None else 5,
        table=table,
        special_sources=special_sources,
    )

    if diagnostics is not None:
        diagnostics.add(
            source.panden.loc[~source.panden.index.isin(classes.index)],
            source="BAG",
            layer=pand_layer,
            source_path=bag_gpkg,
            stage="Pandstatus",
            reason="Pandstatus ontbreekt of is niet geselecteerd volgens de notitie.",
            value_column="status",
            id_column="identificatie",
        )

    # Preserve the existing representative-point rule for dike location.
    classes["binnendijks"] = classes.geometry.representative_point().covered_by(
        dike_area
    )
    classes["code"] = (
        classes["lgb_code_binnendijks"]
        .where(classes["binnendijks"], classes["lgb_code_buitendijks"])
        .fillna(0)
        .astype("uint8")
    )
    unresolved = int((classes["klasse_status"] == "nog te beoordelen").sum())
    logger.info(
        "BAG: %s selected panden, %s unresolved (NoData)",
        len(classes),
        unresolved,
    )
    if include_details:
        return classes
    return classes[["geometry", "code"]]


def prepare_gemalen(
    gpkg: Path,
    *,
    layer: str = "gemaal",
    capacity_column: str = "maximalecapaciteit",
    bounds: tuple[float, float, float, float],
    crs: str,
    dike_area: BaseGeometry | None = None,
    table: LanduseTable | None = None,
    include_details: bool = False,
    diagnostics: LanduseDiagnostics | None = None,
) -> gpd.GeoDataFrame:
    """Read and classify gemaal points using capacity in m3/min.

    Parameters
    ----------
    gpkg : pathlib.Path
        Existing gemalen GeoPackage. No download is started.
    layer, capacity_column : str, optional
        Point layer and capacity field. Defaults match the HyDAMO source.
    bounds : tuple of float
        Read bounds in the given CRS.
    crs : str
        Expected source and bounds CRS; mismatches raise ValueError.
    dike_area : BaseGeometry, optional
        Inside/outside classification. Omitted for control of both possible codes.
    table : LanduseTable, optional
        CSV codes; defaults to the packaged table.
    include_details : bool, optional
        Return all records, including unclassified stations and their reasons.
    diagnostics : LanduseDiagnostics, optional
        Behoud bron-FID's voor controle. Niet-ingedeelde punten worden in de
        rasterbouw pas na de BAG-koppeling verzameld.

    Returns
    -------
    geopandas.GeoDataFrame
        Classified points, or all source and decision columns when requested.
        Points retain their original location and rasterize to one cell, without
        a buffer or BAG match. Without dike_area no final code is assigned.
    """
    source_crs = pyogrio.read_info(gpkg, layer=layer)["crs"]
    if source_crs is None or not same_crs(source_crs, crs):
        raise ValueError(f"Onverwacht CRS voor gemalen: {source_crs}")
    data = wgpd.read_file(
        gpkg, layer=layer, bbox=bounds, fid_as_index=diagnostics is not None
    )
    if not data.geometry.dropna().geom_type.eq("Point").all():
        raise ValueError("De gemalenlaag moet puntgeometrie bevatten.")
    result = classify_pumping_stations(
        data, capacity_column=capacity_column, table=table
    )
    if dike_area is not None:
        result["binnendijks"] = result.geometry.covered_by(dike_area)
        result["code"] = result["lgb_code_binnendijks"].where(
            result["binnendijks"], result["lgb_code_buitendijks"]
        )
    logger.info(
        "Gemalen: %s van %s punten ingedeeld op capaciteit",
        int(result["lgb_koppeling_id"].notna().sum()),
        len(result),
    )
    if include_details or dike_area is None:
        return result
    return result.loc[result["code"].notna(), ["geometry", "code"]]
