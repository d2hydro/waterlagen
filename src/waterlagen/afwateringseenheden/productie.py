"""Complete afwateringseenheden production for a shared input area."""

from pathlib import Path

from shapely.ops import unary_union

from waterlagen._production import _file_identity, production_run, validate_run_target
from waterlagen._sources import SourcePreparation, source_options
from waterlagen.afwateringseenheden import (
    calculate_afwateringseenheden_tiles,
    prepare_watersysteem,
    write_watersysteem,
)
from waterlagen.afwateringseenheden.brandlagen import (
    _brand_identity,
    _prepare_brandlagen,
)
from waterlagen.afwateringseenheden.config import BrandlagenConfig
from waterlagen.afwateringseenheden.sources import (
    CONNECTION_POLICY,
    SOURCE_POLICY,
    read_watersysteem_sources,
    validate_authority_options,
)
from waterlagen.afwateringseenheden.pcraster import require_pcraster
from waterlagen.afwateringseenheden.raster import _grid_for_square
from waterlagen.afwateringseenheden.tiles import (
    _calculation_geometry,
    _tiles_for_gebied,
)
from waterlagen.ahn.productie import prepare_ahn
from waterlagen.areas import (
    Area,
    ProductionArea,
    area_name,
    ensure_land_boundary,
    resolve_area,
    resolve_workers,
)
from waterlagen.datastore import DataStore
from waterlagen.hydamo import download_hydamo
from waterlagen.logger import get_logger
from waterlagen.rijkswateren.download import RIJKSWATEREN_URL, download_rijkswateren
from waterlagen.settings import settings

logger = get_logger(__name__)


def main(
    data_store: DataStore | None = None,
    *,
    area: str | Area | ProductionArea = Area.nederland,
    workers: int | None = None,
    run_id: str | None = None,
    resume: bool = False,
    overwrite: bool = False,
    refresh_sources: bool = False,
    offline: bool = False,
    preparation: SourcePreparation | None = None,
    brandlagen: BrandlagenConfig | None = None,
    overige_waterschappen: bool = False,
    eigen_hydamo: Path | None = None,
    rijkswateren_url: str = RIJKSWATEREN_URL,
) -> Path:
    """Produce full tiles with separate drainage targets and surrounding burn context.

    Parameters
    ----------
    data_store : DataStore, optional
        Source and output locations.
    area : str or Area or ProductionArea
        Input selection; results are not clipped to this boundary. A water
        authority code also selects that authority's primary drainage targets.
    workers : int, optional
        Override the configured number of processes.
    run_id : str, optional
        Unique output run, default a UTC timestamp.
    resume, overwrite : bool
        Reuse or rebuild a compatible existing run.
    refresh_sources, offline : bool
        Refresh sources for a new run, or require local sources.
    preparation : SourcePreparation, optional
        Shared source policy for nested productions.
    brandlagen : BrandlagenConfig, optional
        User-supplied optional burn layers. Checked before AHN preparation.
        Recorded source identities and defaults must match when resuming a run.
    overige_waterschappen : bool, optional
        Include surrounding water authorities as targets, default False. Requires
        an authority area. RWS remains burn context when an authority is chosen.
    eigen_hydamo : pathlib.Path, optional
        Complete hydroobject/gemaal/stuw replacement for the selected authority.
        Validated before AHN preparation. Requires an authority area.
    rijkswateren_url : str, optional
        Published RWS source location. Local sources are reused unless refresh
        is requested. Without an authority code, RWS also supplies targets.

    Returns
    -------
    pathlib.Path
        Combined afwateringseenheden GeoPackage.
    """
    name = area_name(area)
    code = name.removeprefix("waterschap_") if name.startswith("waterschap_") else None
    validate_authority_options(code, overige_waterschappen, eigen_hydamo)
    require_pcraster()
    store = data_store or DataStore()
    validate_run_target(
        store.processed_data_dir,
        "afwateringseenheden",
        area_name(area),
        run_id,
        resume=resume,
        overwrite=overwrite,
    )
    preparation = source_options(
        preparation,
        refresh_sources=refresh_sources,
        offline=offline,
        resume=resume,
        overwrite=overwrite,
    )
    selected = resolve_area(area, store, preparation)
    workers = resolve_workers(workers, settings.afwateringseenheden_workers)
    tile_size, tile_buffer = 10000, 2000
    tiles = _tiles_for_gebied(
        selected.geometry, tile_size_m=tile_size, origin_x=0, origin_y=0
    )
    context = unary_union(
        [_calculation_geometry(tile, tile_buffer_m=tile_buffer) for tile in tiles]
    )
    parameters = {
        "area": selected.identity,
        "crs": settings.crs,
        "tile_size_m": tile_size,
        "tile_buffer_m": tile_buffer,
        "burn_depth_m": 100,
        "max_fill_depth_m": 50,
        "random_seed": 12345,
        "waterbeheercode": code,
        "overige_waterschappen": overige_waterschappen,
        "eigen_hydamo": str(Path(eigen_hydamo).resolve())
        if eigen_hydamo is not None
        else None,
        "rijkswateren_url": rijkswateren_url,
        "source_policy": SOURCE_POLICY,
        "source_layers": {
            "gkw": ["hydroobject", "gemaal", "stuw"],
            "rws": ["hydroobject"],
        },
        "secondary_connection_policy": CONNECTION_POLICY,
        "secondary_connection_tolerance_m": 2.0,
        "max_segment_length_m": 500.0,
        "resolution_m": 2.0,
        "burn_categories": ["optional", "secundair", "primair"],
        "clip_to_area": False,
    }
    if brandlagen is not None:
        parameters["brandlagen"] = _brand_identity(brandlagen)
    with production_run(
        store.processed_data_dir,
        "afwateringseenheden",
        selected.value,
        run_id=run_id,
        resume=resume,
        overwrite=overwrite,
        parameters=parameters,
    ) as run:
        if brandlagen is not None:
            grids = [
                _grid_for_square(
                    _calculation_geometry(tile, tile_buffer_m=tile_buffer),
                    resolution_m=2,
                )
                for tile in tiles
            ]
            _prepare_brandlagen(
                brandlagen, grids, run.path / "tiles" / "brandlagen.gpkg"
            )
        boundary = ensure_land_boundary(store, preparation)
        hydamo = store.source_data_dir / "hydamo" / "hydamo.gpkg"
        preparation.ensure(
            hydamo,
            lambda: download_hydamo(
                download_dir=hydamo.parent,
                overwrite=preparation.refresh,
                progress=False,
            ),
        )
        rijkswateren = store.hydamo_dir / "rws_hydamo.gpkg"
        preparation.ensure(
            rijkswateren,
            lambda: download_rijkswateren(
                store.hydamo_dir,
                source_url=rijkswateren_url,
                overwrite=preparation.refresh,
                progress=False,
            ),
        )
        source_paths = {"hydamo": hydamo, "rijkswateren": rijkswateren}
        if eigen_hydamo is not None:
            source_paths["eigen_hydamo"] = Path(eigen_hydamo)
        for label, path in list(source_paths.items()):
            source_paths[f"{label}_wal"] = Path(str(path) + "-wal")
        source_identity = {
            name: _file_identity(path) for name, path in source_paths.items()
        }
        previous_inputs = run.metadata.get("inputs")
        if previous_inputs is not None and any(
            previous_inputs.get(name) != identity
            for name, identity in source_identity.items()
        ):
            raise ValueError(
                "Runfolder heeft andere bronbestanden. Kies een nieuwe --run-id."
            )
        sources = read_watersysteem_sources(
            hydamo,
            rijkswateren,
            spatial_selection=context,
            waterbeheercode=code,
            overige_waterschappen=overige_waterschappen,
            eigen_hydamo=eigen_hydamo,
        )
        ahn = prepare_ahn(store, context, run.path / "input" / "ahn.vrt", preparation)
        inputs = {
            **source_paths,
            "ahn": ahn,
            "landsgrens": boundary,
        }
        if source_identity != {
            name: _file_identity(path) for name, path in source_paths.items()
        }:
            raise ValueError(
                "Watersysteem sources changed during preparation; retry with stable sources"
            )
        if brandlagen is not None:
            inputs.update(
                {
                    f"brandlaag_{i}": source.path
                    for i, source in enumerate(brandlagen.lagen)
                }
            )
        run.record_inputs(inputs)
        network = prepare_watersysteem(sources.targets, sources.points)
        network_path = write_watersysteem(
            hydroobject_primair=sources.primary,
            hydroobject_secundair=sources.secondary,
            watersysteem=network,
            output_path=run.path / "watersysteem.gpkg",
            overwrite=overwrite,
        )
        result = calculate_afwateringseenheden_tiles(
            selected.geometry,
            burn_depth_m=100,
            max_fill_depth_m=50,
            random_seed=12345,
            ahn_vrt_path=ahn,
            landsgrens_path=boundary,
            watersysteem_path=network_path,
            output_dir=run.path / "tiles",
            merged_output_path=run.path / "afwateringseenheden.gpkg",
            tile_size_m=tile_size,
            tile_buffer_m=tile_buffer,
            workers=workers,
            overwrite=overwrite,
            clip_to_area=False,
            brandlagen=brandlagen,
        )
        if result.merged_path is None:
            raise ValueError("Geen afwateringseenheden geproduceerd voor dit gebied")
        logger.info("Afwateringseenheden voltooid: %s", result.merged_path)
        return result.merged_path
