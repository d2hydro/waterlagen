"""Bronnen indelen, in vaste volgorde rasteriseren en één rastertegel schrijven."""

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyogrio
import rasterio as rio
from rasterio.enums import Resampling
from shapely.geometry.base import BaseGeometry

from waterlagen import _geopandas as wgpd
from waterlagen import datastore as default_datastore
from waterlagen._crs import same_crs
from waterlagen.bag import download_bag_light
from waterlagen.bgt import download_bgt
from waterlagen.brp import download_brp
from waterlagen.datastore import DataStore
from waterlagen.dijkringen import download_dijkringen
from waterlagen.functioneel_landgebruik.bag_panden_en_verblijfsobjecten import (
    _bounds_including_panden,
)
from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import (
    prepare_bag,
    prepare_bgt_layer,
    prepare_brp,
    prepare_functionele_gebieden,
    prepare_gemalen,
    prepare_water,
    prepare_wegen,
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
    dijkringen_gpkg: Path = field(
        default_factory=lambda: (
            default_datastore.dijkringen_dir / "dijkringen_historie_2012.gpkg"
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
        return cls(
            bgt_gpkg=data_store.bgt_dir / "bgt.gpkg",
            bag_gpkg=data_store.bag_dir / "bag-light.gpkg",
            brp_gpkg=data_store.brp_dir / "brpgewaspercelen_definitief_2025.gpkg",
            top10nl_gpkg=data_store.top10nl_dir / "top10nl_Compleet.gpkg",
            dijkringen_gpkg=data_store.dijkringen_dir / "dijkringen_historie_2012.gpkg",
            gemalen_gpkg=gemalen_gpkg,
        )


@dataclass(frozen=True)
class FunctioneelLandgebruikLayers:
    """Layer names expected in the functional land-use source GeoPackages."""

    bgt_water: str = "bgt_waterdeel"
    bgt_wegdeel: str = "bgt_wegdeel"
    bgt_ondersteunendwegdeel: str = "bgt_ondersteunendwegdeel"
    bgt_begroeidterreindeel: str = "bgt_begroeidterreindeel"
    bgt_onbegroeidterreindeel: str = "bgt_onbegroeidterreindeel"
    bag_pand: str = "pand"
    bag_verblijfsobject: str = "verblijfsobject"
    brp: str = "brp_gewas"
    top10nl_functioneel_gebied: str = "top10nl_functioneel_gebied_vlak"
    dijkringen: str = "dijkring_v_2012"
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
    if not sources.bgt_gpkg.exists():
        download_bgt(
            download_dir=sources.bgt_gpkg.parent,
            target_path=sources.bgt_gpkg,
            featuretypes=[
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

    if not sources.dijkringen_gpkg.exists():
        download_dijkringen(
            download_dir=sources.dijkringen_gpkg.parent,
            target_path=sources.dijkringen_gpkg,
            overwrite=False,
        )


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


def _read_dike_area(
    sources: FunctioneelLandgebruikSources,
    layers: FunctioneelLandgebruikLayers,
) -> BaseGeometry:
    """Read and dissolve the dike-ring geometry used for inside/outside classes."""
    dijkringen = wgpd.read_file(sources.dijkringen_gpkg, layer=layers.dijkringen)
    if dijkringen.crs is None or not same_crs(dijkringen.crs, settings.crs):
        raise ValueError(
            f"CRS van dijkringen ({dijkringen.crs}) verschilt van {settings.crs}."
        )
    return dijkringen.geometry.make_valid().union_all()


def _prepare_buildings_and_pumps(
    sources: FunctioneelLandgebruikSources,
    layers: FunctioneelLandgebruikLayers,
    *,
    bounds: tuple[float, float, float, float],
    dike_area: BaseGeometry,
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
        dike_area=dike_area,
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
            dike_area=dike_area,
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
    return [buildings[["geometry", "code"]], *gemalen]


def _prepare_priority_sources(
    sources: FunctioneelLandgebruikSources,
    layers: FunctioneelLandgebruikLayers,
    *,
    bounds: tuple[float, float, float, float],
    dike_area: BaseGeometry,
    table: LanduseTable,
    diagnostics: LanduseDiagnostics | None = None,
) -> list[gpd.GeoDataFrame]:
    """Bereid bronlagen voor; de laatste laag wint bij overlap in het raster."""
    required_layers = {
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
        dike_area=dike_area,
        table=table,
        diagnostics=diagnostics,
    )
    terrains = [
        prepare_bgt_layer(
            sources.bgt_gpkg,
            layer=actual_layer,
            mapping_layer=mapping_layer,
            bounds=bounds,
            dike_area=dike_area,
            table=table,
            diagnostics=diagnostics,
        )
        for actual_layer, mapping_layer in [
            (layers.bgt_begroeidterreindeel, "bgt_begroeidterreindeel"),
            (layers.bgt_onbegroeidterreindeel, "bgt_onbegroeidterreindeel"),
        ]
    ]
    functional_areas = [
        prepare_functionele_gebieden(
            sources.top10nl_gpkg,
            layer=layer,
            bounds=bounds,
            dike_area=dike_area,
            table=table,
            diagnostics=diagnostics,
        )
        for layer in (
            layers.top10nl_functioneel_gebied,
            layers.top10nl_functioneel_gebied_multivlak,
        )
    ]
    agriculture = prepare_brp(
        sources.brp_gpkg,
        layer=layers.brp,
        bounds=bounds,
        dike_area=dike_area,
        table=table,
        diagnostics=diagnostics,
    )
    road_support = prepare_bgt_layer(
        sources.bgt_gpkg,
        layer=layers.bgt_ondersteunendwegdeel,
        mapping_layer="bgt_ondersteunendwegdeel",
        bounds=bounds,
        dike_area=dike_area,
        table=table,
        diagnostics=diagnostics,
    )
    roads = prepare_wegen(
        sources.bgt_gpkg,
        layer=layers.bgt_wegdeel,
        bounds=bounds,
        dike_area=dike_area,
        table=table,
        diagnostics=diagnostics,
    )
    water = prepare_water(
        sources.bgt_gpkg,
        layer=layers.bgt_water,
        bounds=bounds,
        dike_area=dike_area,
        table=table,
        diagnostics=diagnostics,
    )
    # Water gaat voor wegen, gebouwen en landbouw (notitie p. 10).
    # De rest is de huidige verwerkingsvolgorde, geen volledige notitieregel.
    # Gebouwen met een open klasse schrijven NoData over eerder ingetekend terrein.
    return [
        *terrains,
        *functional_areas,
        agriculture,
        road_support,
        roads,
        *buildings_and_pumps,
        water,
    ]


def bouw_functioneel_landgebruik(
    target_path: Path,
    *,
    bounds: tuple[float, float, float, float],
    resolution_m: float = 0.5,
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
) -> Path:
    """Build a functional land-use GeoTIFF for one requested extent.

    The workflow prepares all configured vector sources for the requested
    bounds, classifies their attributes to the functional land-use legend,
    rasterizes them in priority order, and writes a paletted GeoTIFF with
    overviews. Source geometries are read with the requested bounds as a bbox
    filter. Top10NL, BRP, BGT roads, and BAG classes are additionally adjusted
    for whether their representative point lies inside the configured dike-ring
    area.

    Parameters
    ----------
    target_path : Path
        GeoTIFF path to write.
    bounds : tuple[float, float, float, float]
        Output bounds as ``(xmin, ymin, xmax, ymax)`` in ``crs``.
    resolution_m : float, optional
        Raster cell size in map units, by default 0.5.
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

    Returns
    -------
    Path
        The written or reused ``target_path``.

    Side Effects
    ------------
    May download missing BGT, BAG, BRP, Top10NL, and dijkringen source files to
    the configured datastore paths. The GeoTIFF is written to a temporary file
    beside ``target_path`` and atomically replaces the target after successful
    raster creation. A same-stem QGIS ``.qml`` file with category labels is
    written for newly produced rasters. Reused rasters and styles are unchanged.
    """
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
    dike_area = _read_dike_area(sources, layers)

    nodata = 0
    raster = np.full(
        (grid.height, grid.width),
        fill_value=nodata,
        dtype=np.uint8,
    )
    diagnostics = LanduseDiagnostics() if diagnostics_path is not None else None
    for data in _prepare_priority_sources(
        sources,
        layers,
        bounds=grid.bounds,
        dike_area=dike_area,
        table=table,
        diagnostics=diagnostics,
    ):
        rasterize_features(raster, data, grid.transform)

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
