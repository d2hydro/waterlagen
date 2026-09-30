"""Bronnen indelen, in vaste volgorde rasteriseren en één rastertegel schrijven."""

import os
import tempfile
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from uuid import uuid4

import geopandas as gpd
import numpy as np
import pyogrio
import rasterio as rio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from shapely.geometry.base import BaseGeometry

from waterlagen import _geopandas as wgpd
from waterlagen import datastore as default_datastore
from waterlagen._crs import same_crs
from waterlagen.administratieve_gebieden import read_landsgrens
from waterlagen.bag import download_bag_light
from waterlagen.bgt import download_bgt
from waterlagen.brp import download_brp
from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik.aanvullen import (
    _fill_gaps,
    _fill_metadata,
    _source_path,
    _validate_outputs,
    _validate_radius,
)
from waterlagen.functioneel_landgebruik.bag_panden_en_verblijfsobjecten import (
    _bounds_including_panden,
)
from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import (
    _prepare_top10nl_layer,
    prepare_bag,
    prepare_bgt_layer,
    prepare_brp,
    prepare_functionele_gebieden,
    prepare_gemalen,
    prepare_water,
    prepare_wegen,
)
from waterlagen.functioneel_landgebruik.gebouwen import (
    identify_buildings,
    validate_buildings,
    write_buildings,
)
from waterlagen.functioneel_landgebruik.gemalen import link_pumping_stations
from waterlagen.functioneel_landgebruik.kassen_rwzi_drinkwater import (
    SpecialBuildingSources,
)
from waterlagen.functioneel_landgebruik.landgebruikstabel import (
    LanduseTable,
    load_landuse_table,
)
from waterlagen.functioneel_landgebruik.legenda import build_colormap, write_qgis_style
from waterlagen.functioneel_landgebruik.nodata_verklaren import (
    LanduseDiagnostics,
    validate_diagnostics,
)
from waterlagen.functioneel_landgebruik.rasteriseren import rasterize_features
from waterlagen.logger import get_logger
from waterlagen.raster.config import RasterOutputConfig
from waterlagen.raster.grid import RasterGrid
from waterlagen.raster.overviews import build_raster_overviews
from waterlagen.settings import settings
from waterlagen.top10nl import download_top10nl

logger = get_logger(__name__)


@dataclass(frozen=True)
class FunctioneelLandgebruikSources:
    """Input GeoPackage paths for the functional land-use build workflow."""

    bgt_gpkg: Path = field(
        default_factory=lambda: default_datastore.bgt_dir / "bgt.gpkg"
    )
    bag_gpkg: Path = field(
        default_factory=lambda: default_datastore.bag_dir / "bag-light.gpkg"
    )
    brp_gpkg: Path = field(
        default_factory=lambda: (
            default_datastore.brp_dir / "brpgewaspercelen_definitief_2025.gpkg"
        )
    )
    top10nl_gpkg: Path = field(
        default_factory=lambda: default_datastore.top10nl_dir / "top10nl_Compleet.gpkg"
    )
    buitendijks_gpkg: Path = field(
        default_factory=lambda: (
            default_datastore.source_data_dir
            / "liwo"
            / "buitendijks_gebied_uit_liwo.gpkg"
        )
    )
    rwzi_gpkg: Path | None = None
    drinking_water_gpkg: Path | None = None
    gemalen_gpkg: Path | None = None

    @classmethod
    def from_datastore(cls, data_store: DataStore) -> "FunctioneelLandgebruikSources":
        """Create source paths rooted in an explicitly supplied datastore."""
        gemalen_gpkg = data_store.source_data_dir / "hydamo" / "hydamo.gpkg"
        if not gemalen_gpkg.is_file():
            gemalen_gpkg = None
        rwzi_gpkg = (
            data_store.source_data_dir / "waterketen_damo" / "waterketen_damo.gpkg"
        )
        if not rwzi_gpkg.is_file():
            rwzi_gpkg = None
        drinking_water_gpkg = (
            data_store.source_data_dir / "osm" / "drinkwaterlocaties.gpkg"
        )
        if not drinking_water_gpkg.is_file():
            drinking_water_gpkg = None
        return cls(
            bgt_gpkg=data_store.bgt_dir / "bgt.gpkg",
            bag_gpkg=data_store.bag_dir / "bag-light.gpkg",
            brp_gpkg=data_store.brp_dir / "brpgewaspercelen_definitief_2025.gpkg",
            top10nl_gpkg=data_store.top10nl_dir / "top10nl_Compleet.gpkg",
            buitendijks_gpkg=data_store.source_data_dir
            / "liwo"
            / "buitendijks_gebied_uit_liwo.gpkg",
            drinking_water_gpkg=drinking_water_gpkg,
            gemalen_gpkg=gemalen_gpkg,
            rwzi_gpkg=rwzi_gpkg,
        )


@dataclass(frozen=True)
class FunctioneelLandgebruikLayers:
    """Layer names expected in the functional land-use source GeoPackages."""

    bgt_ondersteunendwaterdeel: str = "bgt_ondersteunendwaterdeel"
    bgt_water: str = "bgt_waterdeel"
    bgt_wegdeel: str = "bgt_wegdeel"
    bgt_ondersteunendwegdeel: str = "bgt_ondersteunendwegdeel"
    bgt_begroeidterreindeel: str = "bgt_begroeidterreindeel"
    bgt_onbegroeidterreindeel: str = "bgt_onbegroeidterreindeel"
    bag_pand: str = "pand"
    bag_verblijfsobject: str = "verblijfsobject"
    brp: str = "brp_gewas"
    top10nl_functioneel_gebied: str = "top10nl_functioneel_gebied_vlak"
    buitendijks: str = "buitendijks_gebied_uit_liwo"
    top10nl_terrein: str = "top10nl_terrein_vlak"
    top10nl_gebouw: str = "top10nl_gebouw_vlak"
    rwzi: str = "rwzi"
    rwzi_status_column: str = "status"
    rwzi_active_value: str = "in gebruik"
    drinking_water: str = "drinkwaterproductieterrein"
    gemalen: str = "gemaal"
    gemaal_capacity_column: str = "maximalecapaciteit"
    top10nl_functioneel_gebied_multivlak: str = "top10nl_functioneel_gebied_multivlak"


def _profile_for_grid(grid: RasterGrid, *, output_config: RasterOutputConfig) -> dict:
    """Create the GeoTIFF profile used for functional land-use raster output."""
    return {
        "driver": "GTiff",
        "photometric": "PALETTE",
        "count": 1,
        "dtype": "uint8",
        "nodata": 0,
        "width": grid.width,
        "height": grid.height,
        "transform": grid.transform,
        "crs": grid.crs,
        "tiled": True,
        "blockxsize": output_config.block_size,
        "blockysize": output_config.block_size,
        "compress": "ZSTD",
        "zstd_level": 9,
        "predictor": 2,
        "interleave": "band",
        "bigtiff": "IF_SAFER",
    }


def _download_missing_sources(
    sources: FunctioneelLandgebruikSources,
    layers: FunctioneelLandgebruikLayers,
) -> None:
    """Download source datasets that are missing from the configured paths."""
    if not sources.buitendijks_gpkg.is_file():
        raise FileNotFoundError(
            f"LIWO source missing: {sources.buitendijks_gpkg}. Run scripts/liwo_overstromingsgevoelige_gebieden.py first."
        )
    if not sources.bgt_gpkg.exists():
        download_bgt(
            download_dir=sources.bgt_gpkg.parent,
            target_path=sources.bgt_gpkg,
            featuretypes=[
                layers.bgt_ondersteunendwaterdeel.removeprefix("bgt_"),
                layers.bgt_water.removeprefix("bgt_"),
                layers.bgt_wegdeel.removeprefix("bgt_"),
                layers.bgt_ondersteunendwegdeel.removeprefix("bgt_"),
                layers.bgt_begroeidterreindeel.removeprefix("bgt_"),
                layers.bgt_onbegroeidterreindeel.removeprefix("bgt_"),
            ],
            overwrite=False,
        )

    if not sources.bag_gpkg.exists():
        download_bag_light(download_dir=sources.bag_gpkg.parent, overwrite=False)

    if not sources.brp_gpkg.exists():
        download_brp(
            download_dir=sources.brp_gpkg.parent,
            filename=sources.brp_gpkg.name,
            overwrite=False,
        )

    if not sources.top10nl_gpkg.exists():
        download_top10nl(download_dir=sources.top10nl_gpkg.parent, overwrite=False)


def _validate_sources_exist(sources: FunctioneelLandgebruikSources) -> None:
    """Raise a clear error when one or more configured source datasets are absent."""
    missing = [
        path
        for path in sources.__dict__.values()
        if path is not None and not Path(path).exists()
    ]
    if missing:
        labels = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing source dataset(s): {labels}")


def _read_buitendijks_area(
    sources: FunctioneelLandgebruikSources,
    layers: FunctioneelLandgebruikLayers,
) -> BaseGeometry:
    """Read and dissolve LIWO polygons used as the sole outside-area source."""
    buitendijks = wgpd.read_file(sources.buitendijks_gpkg, layer=layers.buitendijks)
    if buitendijks.crs is None or not same_crs(buitendijks.crs, settings.crs):
        raise ValueError(
            f"CRS van LIWO buitendijks ({buitendijks.crs}) verschilt van {settings.crs}."
        )
    if (
        not buitendijks.geometry.dropna()
        .geom_type.isin(["Polygon", "MultiPolygon"])
        .all()
    ):
        raise ValueError("LIWO buitendijks moet polygonen bevatten")
    return buitendijks.geometry.dropna().make_valid().union_all()


def _prepare_buildings_and_pumps(
    sources: FunctioneelLandgebruikSources,
    layers: FunctioneelLandgebruikLayers,
    *,
    bounds: tuple[float, float, float, float],
    buitendijks_area: BaseGeometry,
    table: LanduseTable,
    diagnostics: LanduseDiagnostics | None = None,
) -> list[gpd.GeoDataFrame]:
    """Bereid BAG voor, pas gemaalklassen toe en behoud ongekoppelde punten."""
    special_sources = SpecialBuildingSources(
        top10nl_gpkg=sources.top10nl_gpkg,
        greenhouse_layer=layers.top10nl_gebouw,
        rwzi_gpkg=sources.rwzi_gpkg,
        rwzi_layer=layers.rwzi,
        rwzi_status_column=layers.rwzi_status_column,
        rwzi_active_value=layers.rwzi_active_value,
        drinking_water_gpkg=sources.drinking_water_gpkg,
        drinking_water_layer=layers.drinking_water,
    )
    buildings = prepare_bag(
        sources.bag_gpkg,
        pand_layer=layers.bag_pand,
        verblijfsobject_layer=layers.bag_verblijfsobject,
        bounds=bounds,
        buitendijks_area=buitendijks_area,
        table=table,
        special_sources=special_sources,
        include_details=True,
        diagnostics=diagnostics,
    )
    gemalen = []
    if sources.gemalen_gpkg is not None:
        pump_bounds = _bounds_including_panden(bounds, buildings)
        stations = prepare_gemalen(
            sources.gemalen_gpkg,
            layer=layers.gemalen,
            capacity_column=layers.gemaal_capacity_column,
            bounds=pump_bounds,
            crs=settings.crs,
            buitendijks_area=buitendijks_area,
            table=table,
            include_details=True,
            diagnostics=diagnostics,
        )
        linked = link_pumping_stations(buildings, stations, table=table)
        buildings = linked.panden
        buildings["code"] = (
            buildings["lgb_code_binnendijks"]
            .where(buildings["binnendijks"], buildings["lgb_code_buitendijks"])
            .fillna(0)
            .astype("uint8")
        )
        points = linked.gemalen
        if diagnostics is not None:
            diagnostics.add(
                points.loc[
                    points["geometrie_kaart"].eq("punt") & points["code"].isna()
                ],
                source="HyDAMO",
                layer=layers.gemalen,
                source_path=sources.gemalen_gpkg,
                stage="Gemaalcapaciteit",
                reason=points["reden_capaciteitsklasse"],
                value_column="capaciteit_m3_min",
                id_column="globalid" if "globalid" in points else None,
                details=points["reden_ruimtelijke_koppeling"],
            )
        gemalen.append(
            points.loc[
                points["geometrie_kaart"].eq("punt") & points["code"].notna(),
                ["geometry", "code"],
            ]
        )
    else:
        logger.warning("Gemalen overgeslagen: geen gemalenbestand geconfigureerd")
    if diagnostics is not None:
        diagnostics.add_unclassified_buildings(
            buildings, source_path=sources.bag_gpkg, layer=layers.bag_pand
        )
    return [buildings[["geometry", "code", "identificatie"]], *gemalen]


def _prepare_priority_sources(
    sources: FunctioneelLandgebruikSources,
    layers: FunctioneelLandgebruikLayers,
    *,
    bounds: tuple[float, float, float, float],
    buitendijks_area: BaseGeometry,
    table: LanduseTable,
    diagnostics: LanduseDiagnostics | None = None,
    building_context_m: float = 0.0,
) -> list[gpd.GeoDataFrame]:
    """Bereid bronlagen voor; de laatste laag wint bij overlap in het raster."""
    required_layers = {
        layers.bgt_ondersteunendwaterdeel,
        layers.bgt_water,
        layers.bgt_wegdeel,
        layers.bgt_ondersteunendwegdeel,
        layers.bgt_begroeidterreindeel,
        layers.bgt_onbegroeidterreindeel,
    }
    available_layers = set(pyogrio.list_layers(sources.bgt_gpkg)[:, 0])
    missing = required_layers - available_layers
    if missing:
        raise ValueError(
            "BGT-GeoPackage mist lagen voor de CSV-indeling: "
            + ", ".join(sorted(missing))
            + ". Vul het bronbestand aan; bestaande downloads worden niet vervangen."
        )
    logger.info("Voorbereiden van CSV-landgebruik, inclusief bijzondere gebouwen")
    buildings_and_pumps = _prepare_buildings_and_pumps(
        sources,
        layers,
        bounds=bounds,
        buitendijks_area=buitendijks_area,
        table=table,
        diagnostics=diagnostics,
    )
    if building_context_m and not buildings_and_pumps[0].empty:
        # Neighbours of complete crossing footprints are needed to exclude all
        # building donors. The land-use work grid itself remains unchanged.
        xmin, ymin, xmax, ymax = _bounds_including_panden(
            bounds, buildings_and_pumps[0]
        )
        context_bounds = (
            xmin - building_context_m,
            ymin - building_context_m,
            xmax + building_context_m,
            ymax + building_context_m,
        )
        buildings_and_pumps = _prepare_buildings_and_pumps(
            sources,
            layers,
            bounds=context_bounds,
            buitendijks_area=buitendijks_area,
            table=table,
            diagnostics=None,
        )
    terrains = [
        prepare_bgt_layer(
            sources.bgt_gpkg,
            layer=actual_layer,
            mapping_layer=mapping_layer,
            bounds=bounds,
            buitendijks_area=buitendijks_area,
            table=table,
            diagnostics=diagnostics,
        )
        for actual_layer, mapping_layer in [
            (layers.bgt_ondersteunendwaterdeel, "bgt_ondersteunendwaterdeel"),
            (layers.bgt_begroeidterreindeel, "bgt_begroeidterreindeel"),
            (layers.bgt_onbegroeidterreindeel, "bgt_onbegroeidterreindeel"),
        ]
    ]
    functional_areas = [
        prepare_functionele_gebieden(
            sources.top10nl_gpkg,
            layer=layer,
            bounds=bounds,
            buitendijks_area=buitendijks_area,
            table=table,
            diagnostics=diagnostics,
        )
        for layer in (
            layers.top10nl_functioneel_gebied,
            layers.top10nl_functioneel_gebied_multivlak,
        )
    ]
    top10_terrain = _prepare_top10nl_layer(
        sources.top10nl_gpkg,
        layer=layers.top10nl_terrein,
        mapping_layer="top10nl_terrein_vlak",
        bounds=bounds,
        buitendijks_area=buitendijks_area,
        table=table,
        diagnostics=diagnostics,
    )
    agriculture = prepare_brp(
        sources.brp_gpkg,
        layer=layers.brp,
        bounds=bounds,
        buitendijks_area=buitendijks_area,
        table=table,
        diagnostics=diagnostics,
    )
    road_support = prepare_bgt_layer(
        sources.bgt_gpkg,
        layer=layers.bgt_ondersteunendwegdeel,
        mapping_layer="bgt_ondersteunendwegdeel",
        bounds=bounds,
        buitendijks_area=buitendijks_area,
        table=table,
        diagnostics=diagnostics,
    )
    roads = prepare_wegen(
        sources.bgt_gpkg,
        layer=layers.bgt_wegdeel,
        bounds=bounds,
        buitendijks_area=buitendijks_area,
        table=table,
        diagnostics=diagnostics,
    )
    water = prepare_water(
        sources.bgt_gpkg,
        layer=layers.bgt_water,
        bounds=bounds,
        buitendijks_area=buitendijks_area,
        table=table,
        diagnostics=diagnostics,
    )
    # Water gaat voor wegen, gebouwen en landbouw (notitie p. 10).
    # De rest is de huidige verwerkingsvolgorde, geen volledige notitieregel.
    # Gebouwen met een open klasse schrijven NoData over eerder ingetekend terrein.
    prepared = [
        *terrains,
        *functional_areas,
        top10_terrain,
        agriculture,
        road_support,
        roads,
        *buildings_and_pumps,
        water,
    ]
    source_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    if len(buildings_and_pumps) > 1:
        source_ids.append(11)
    source_ids.append(12)
    for data, source_id in zip(prepared, source_ids, strict=True):
        data["source_code"] = source_id
    return prepared


def bouw_functioneel_landgebruik(
    target_path: Path,
    *,
    bounds: tuple[float, float, float, float],
    resolution_m: float = 0.5,
    gap_fill_distance_m: float = 1.0,
    crs: str = settings.crs,
    sources: FunctioneelLandgebruikSources | None = None,
    data_store: DataStore | None = None,
    layers: FunctioneelLandgebruikLayers | None = None,
    download_missing_sources: bool | None = None,
    download_missing: bool | None = None,
    overwrite: bool = True,
    output_config: RasterOutputConfig | None = None,
    mapping_csv: Path | None = None,
    diagnostics_path: Path | None = None,
    building_index_path: Path | None = None,
    building_context_m: float = 5.0,
) -> Path:
    """Build a functional land-use GeoTIFF for one requested extent.

    The workflow prepares all configured vector sources for the requested
    bounds, classifies their attributes to the functional land-use legend,
    rasterizes them in priority order, and writes a paletted GeoTIFF with
    overviews. Source geometries are read with the requested bounds as a bbox
    filter. Top10NL, BRP, BGT roads, and BAG classes are additionally adjusted
    using representative points covered by the LIWO outside-area polygons
    (including boundaries). All other locations use inside codes.

    Parameters
    ----------
    target_path : Path
        GeoTIFF path to write.
    bounds : tuple[float, float, float, float]
        Output bounds as ``(xmin, ymin, xmax, ymax)`` in ``crs``.
    resolution_m : float, optional
        Raster cell size in map units, by default 0.5.
    gap_fill_distance_m : float, optional
        Maximum donor distance in metres, default 1.0; zero disables filling.
        A source-ID raster is always written alongside the tile as
        ``functioneel_landgebruik_bronnen.tif`` for standard tile-folder names;
        legacy filenames retain the sibling ``bronnen`` directory.
    crs : str, optional
        CRS voor ``bounds`` en uitvoer. Moet bij een nieuwe berekening
        overeenkomen met :data:`waterlagen.settings.settings.crs`.
    sources : FunctioneelLandgebruikSources, optional
        Explicit source GeoPackage paths. Mutually exclusive with
        ``data_store``.
    data_store : DataStore, optional
        Datastore used to derive default source paths. Mutually exclusive with
        ``sources``.
    layers : FunctioneelLandgebruikLayers, optional
        Source layer names. Defaults to the package layer-name conventions.
    download_missing_sources : bool, optional
        Whether missing source datasets are downloaded before building. If
        omitted, the deprecated ``download_missing`` value is used when given,
        otherwise missing sources are downloaded.
    download_missing : bool, optional
        Backwards-compatible alias for ``download_missing_sources``.
    overwrite : bool, optional
        If False and ``target_path`` already exists, the existing GeoTIFF is
        returned without validating sources, downloading, or rewriting output.
    output_config : RasterOutputConfig, optional
        GeoTIFF block size and overview factors.
    mapping_csv : Path, optional
        Editable land-use table. Defaults to the CSV included in the package.
    diagnostics_path : Path, optional
        GeoPackage met uitsluitend NoData-vlakken en een reden per vlak.
        Alleen geschreven bij een nieuwe berekening. Bij hergebruik van een
        raster zonder controlebestand volgt een foutmelding.
    building_index_path : Path, optional
        Shared building identity lookup from ``ensure_building_index``. Writes
        matched ``gebouw_ids`` rasters and complete prepared ``gebouwen``
        footprints without changing the land-use rasterization or priority.
    building_context_m : float, optional
        Extra prepared neighbours around complete footprints for DEM donor
        exclusion. Must cover the DEM's maximum building search distance.

    Returns
    -------
    Path
        The written or reused ``target_path``.

    Side Effects
    ------------
    May download missing BGT, BAG, BRP and Top10NL source files to
    the configured datastore paths. The GeoTIFF is written to a temporary file
    beside ``target_path`` and atomically replaces the target after successful
    raster creation. A same-stem QGIS ``.qml`` file with category labels is
    written for newly produced rasters. Reused rasters and styles are unchanged.
    """
    _validate_radius(gap_fill_distance_m)
    _validate_radius(building_context_m)
    target_path = Path(target_path)
    if diagnostics_path is not None:
        diagnostics_path = Path(diagnostics_path)
        if diagnostics_path.resolve() == target_path.resolve():
            raise ValueError(
                "Raster en controlebestand moeten verschillende paden hebben."
            )
    if sources is not None and data_store is not None:
        raise ValueError("Pass either sources or data_store, not both")
    sources = sources or (
        FunctioneelLandgebruikSources.from_datastore(data_store)
        if data_store is not None
        else FunctioneelLandgebruikSources.from_datastore(default_datastore)
    )
    layers = layers or FunctioneelLandgebruikLayers()
    output_config = output_config or RasterOutputConfig()
    if download_missing_sources is None:
        download_missing_sources = (
            True if download_missing is None else download_missing
        )

    if target_path.exists() and not overwrite:
        _validate_outputs(target_path, gap_fill_distance_m)
        if building_index_path is not None:
            validate_buildings(target_path, building_context_m)
        if diagnostics_path is not None:
            validate_diagnostics(diagnostics_path, target_path)
        return target_path

    if not same_crs(crs, settings.crs):
        raise ValueError(f"Raster-CRS {crs} verschilt van project-CRS {settings.crs}.")
    table = load_landuse_table(mapping_csv)
    if download_missing_sources:
        _download_missing_sources(sources, layers)
    _validate_sources_exist(sources)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    grid = RasterGrid.from_bounds(bounds, resolution=resolution_m, crs=crs)
    profile = _profile_for_grid(grid, output_config=output_config)
    buitendijks_area = _read_buitendijks_area(sources, layers)

    # Expand on the same pixel grid, then crop both products back to the tile.
    pixel_width, pixel_height = grid.transform.a, -grid.transform.e
    margin = (
        ceil(gap_fill_distance_m / min(pixel_width, pixel_height)) + 1
        if gap_fill_distance_m
        else 0
    )
    work_transform = grid.transform * Affine.translation(-margin, -margin)
    work_width, work_height = grid.width + 2 * margin, grid.height + 2 * margin
    xmin, ymax = work_transform * (0, 0)
    xmax, ymin = work_transform * (work_width, work_height)
    work_bounds = (xmin, ymin, xmax, ymax)
    raster = np.zeros((work_height, work_width), dtype=np.uint8)
    source_raster = np.zeros_like(raster)
    building_ids = (
        np.zeros(raster.shape, dtype="uint32")
        if building_index_path is not None
        else None
    )
    building_records = gpd.GeoDataFrame(
        {"identificatie": [], "gebouw_id": []}, geometry=[], crs=crs
    )
    diagnostics = LanduseDiagnostics() if diagnostics_path is not None else None
    for data in _prepare_priority_sources(
        sources,
        layers,
        bounds=work_bounds,
        buitendijks_area=buitendijks_area,
        table=table,
        diagnostics=diagnostics,
        **(
            # A donor pixel may touch a neighbour beyond its centre's search
            # distance. Include one extra pixel for all_touched exclusion.
            {"building_context_m": building_context_m + max(pixel_width, pixel_height)}
            if building_index_path is not None
            else {}
        ),
    ):
        rasterize_features(raster, data, work_transform)
        rasterize_features(
            source_raster, data, work_transform, value_column="source_code"
        )
        if (
            building_ids is not None
            and not data.empty
            and data["source_code"].eq(10).all()
        ):
            building_records = identify_buildings(data, building_index_path)
            rasterize_features(
                building_ids, building_records, work_transform, value_column="gebouw_id"
            )

    if gap_fill_distance_m:
        landgebied = read_landsgrens()
        if landgebied.crs is None:
            raise ValueError("Landgebied heeft geen CRS.")
        if not same_crs(landgebied.crs, crs):
            landgebied = landgebied.to_crs(crs)
        geometries = [
            geometry
            for geometry in landgebied.geometry.make_valid()
            if geometry is not None and not geometry.is_empty
        ]
        land = (
            geometry_mask(geometries, raster.shape, work_transform, invert=True)
            if geometries
            else np.zeros_like(raster, dtype=bool)
        )
        filled = _fill_gaps(
            raster,
            source_raster,
            land,
            radius_m=gap_fill_distance_m,
            pixel_width=pixel_width,
            pixel_height=pixel_height,
        )
        logger.info(
            "Filled %s gap cells (including tile margin), radius %s m",
            filled,
            gap_fill_distance_m,
        )
    crop = np.s_[margin : margin + grid.height, margin : margin + grid.width]
    raster = raster[crop]
    source_raster = source_raster[crop]
    if building_ids is not None:
        building_ids = building_ids[crop].copy()
        building_ids[source_raster != 10] = 0
        if not np.array_equal(building_ids > 0, source_raster == 10):
            raise ValueError("Building IDs do not match land-use source code 10")

    metadata = _fill_metadata(gap_fill_distance_m) | {"output_pair": uuid4().hex}
    if building_ids is not None:
        metadata["building_context_m"] = str(float(building_context_m))
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=target_path.suffix,
        dir=target_path.parent,
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    tmp_path.unlink(missing_ok=True)
    try:
        with rio.open(tmp_path, "w", **profile) as dst:
            dst.colorinterp = (rio.enums.ColorInterp.palette,)
            dst.write_colormap(1, build_colormap(table))
            dst.write(raster, 1)
            build_raster_overviews(
                dst,
                factors=output_config.overview_factors,
                resampling=Resampling.mode,
            )
            dst.set_band_description(1, "Landgebruik")
            dst.update_tags(**metadata)

        source_path = _source_path(target_path)
        source_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=source_path.parent, suffix=".tif", delete=False
        ) as temporary:
            source_tmp = Path(temporary.name)
        try:
            source_profile = dict(profile)
            source_profile.pop("photometric", None)
            with rio.open(source_tmp, "w", **source_profile) as dst:
                dst.write(source_raster, 1)
                dst.set_band_description(1, "Bron:laag")
                dst.update_tags(**metadata)
                build_raster_overviews(
                    dst,
                    factors=output_config.overview_factors,
                    resampling=Resampling.nearest,
                )
            source_tmp.replace(source_path)
        finally:
            source_tmp.unlink(missing_ok=True)
        if building_ids is not None:
            write_buildings(
                target_path,
                building_ids,
                building_records,
                profile,
                metadata,
                output_config.overview_factors,
            )
        tmp_path.replace(target_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    write_qgis_style(target_path, table)
    if diagnostics is not None:
        diagnostics.write(
            diagnostics_path,
            raster_path=target_path,
            top10nl_gpkg=sources.top10nl_gpkg,
            bgt_gpkg=sources.bgt_gpkg,
        )
    return target_path
