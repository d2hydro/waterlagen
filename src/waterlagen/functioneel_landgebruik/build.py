import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio as rio
from rasterio.enums import Resampling

from waterlagen import _geopandas as wgpd
from waterlagen import datastore as default_datastore
from waterlagen.bag import download_bag_light
from waterlagen.bgt import download_bgt
from waterlagen.brp import download_brp
from waterlagen.dijkringen import download_dijkringen
from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik.legend import COLORMAP
from waterlagen.functioneel_landgebruik.rasterize import rasterize_features
from waterlagen.functioneel_landgebruik.sources import (
    prepare_bag,
    prepare_brp,
    prepare_functionele_gebieden,
    prepare_water,
    prepare_wegen,
)
from waterlagen.raster.config import RasterOutputConfig
from waterlagen.raster.grid import RasterGrid
from waterlagen.raster.overviews import build_raster_overviews
from waterlagen.settings import settings
from waterlagen.top10nl import download_top10nl


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
        default_factory=lambda: default_datastore.brp_dir
        / "brpgewaspercelen_definitief_2025.gpkg"
    )
    top10nl_gpkg: Path = field(
        default_factory=lambda: default_datastore.top10nl_dir / "top10nl_Compleet.gpkg"
    )
    dijkringen_gpkg: Path = field(
        default_factory=lambda: default_datastore.dijkringen_dir
        / "dijkringen_historie_2012.gpkg"
    )

    @classmethod
    def from_datastore(cls, data_store: DataStore) -> "FunctioneelLandgebruikSources":
        """Create source paths rooted in an explicitly supplied datastore."""
        return cls(
            bgt_gpkg=data_store.bgt_dir / "bgt.gpkg",
            bag_gpkg=data_store.bag_dir / "bag-light.gpkg",
            brp_gpkg=data_store.brp_dir / "brpgewaspercelen_definitief_2025.gpkg",
            top10nl_gpkg=data_store.top10nl_dir / "top10nl_Compleet.gpkg",
            dijkringen_gpkg=data_store.dijkringen_dir / "dijkringen_historie_2012.gpkg",
        )


@dataclass(frozen=True)
class FunctioneelLandgebruikLayers:
    """Layer names expected in the functional land-use source GeoPackages."""

    bgt_water: str = "bgt_waterdeel"
    bgt_wegdeel: str = "bgt_wegdeel"
    bag_pand: str = "pand"
    bag_verblijfsobject: str = "verblijfsobject"
    brp: str = "brp_gewas"
    top10nl_functioneel_gebied: str = "top10nl_functioneel_gebied_vlak"
    dijkringen: str = "dijkring_v_2012"


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
    missing = [path for path in sources.__dict__.values() if not Path(path).exists()]
    if missing:
        labels = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing source dataset(s): {labels}")


def _read_dike_area(
    sources: FunctioneelLandgebruikSources,
    layers: FunctioneelLandgebruikLayers,
):
    """Read and dissolve the dike-ring geometry used for inside/outside classes."""
    dijkringen = wgpd.read_file(sources.dijkringen_gpkg, layer=layers.dijkringen)
    return dijkringen.geometry.make_valid().union_all()


def _prepare_priority_sources(
    sources: FunctioneelLandgebruikSources,
    layers: FunctioneelLandgebruikLayers,
    *,
    bounds: tuple[float, float, float, float],
    dike_area,
) -> list[gpd.GeoDataFrame]:
    """Prepare classified vector sources in rasterization priority order."""
    return [
        prepare_functionele_gebieden(
            sources.top10nl_gpkg,
            layer=layers.top10nl_functioneel_gebied,
            bounds=bounds,
            dike_area=dike_area,
        ),
        prepare_brp(
            sources.brp_gpkg,
            layer=layers.brp,
            bounds=bounds,
            dike_area=dike_area,
        ),
        prepare_water(
            sources.bgt_gpkg,
            layer=layers.bgt_water,
            bounds=bounds,
        ),
        prepare_wegen(
            sources.bgt_gpkg,
            layer=layers.bgt_wegdeel,
            bounds=bounds,
            dike_area=dike_area,
        ),
        prepare_bag(
            sources.bag_gpkg,
            pand_layer=layers.bag_pand,
            verblijfsobject_layer=layers.bag_verblijfsobject,
            bounds=bounds,
            dike_area=dike_area,
        ),
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
        Output CRS and the CRS assumed for ``bounds``, by default
        :data:`waterlagen.settings.settings.crs`.
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

    Returns
    -------
    Path
        The written or reused ``target_path``.

    Side Effects
    ------------
    May download missing BGT, BAG, BRP, Top10NL, and dijkringen source files to
    the configured datastore paths. The GeoTIFF is written to a temporary file
    beside ``target_path`` and atomically replaces the target after successful
    raster creation.
    """
    target_path = Path(target_path)
    if sources is not None and data_store is not None:
        raise ValueError("Pass either sources or data_store, not both")
    sources = sources or (
        FunctioneelLandgebruikSources.from_datastore(data_store)
        if data_store is not None
        else FunctioneelLandgebruikSources()
    )
    layers = layers or FunctioneelLandgebruikLayers()
    output_config = output_config or RasterOutputConfig()
    if download_missing_sources is None:
        download_missing_sources = (
            True if download_missing is None else download_missing
        )

    if target_path.exists() and not overwrite:
        return target_path

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
    for data in _prepare_priority_sources(
        sources,
        layers,
        bounds=grid.bounds,
        dike_area=dike_area,
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
            dst.write_colormap(1, COLORMAP)
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

    return target_path
