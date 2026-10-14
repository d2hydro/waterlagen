"""Complete afwateringseenheden production for a shared input area."""

from pathlib import Path

from shapely.geometry import box
from shapely.ops import unary_union

from waterlagen._production import production_run, validate_run_target
from waterlagen._sources import SourcePreparation, source_options
from waterlagen.afwateringseenheden import (
    calculate_afwateringseenheden_tiles,
    prepare_watersysteem,
    read_hydroobjecten,
    read_puntobjecten,
    write_watersysteem,
)
from waterlagen.afwateringseenheden.objects import CATEGORIE_OPPERVLAKTEWATER_COLUMN
from waterlagen.afwateringseenheden.pcraster import require_pcraster
from waterlagen.afwateringseenheden.tiles import _tiles_for_gebied
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
) -> Path:
    """Produce complete tile results using objects from every relevant authority.

    Parameters
    ----------
    data_store : DataStore, optional
        Source and output locations.
    area : str or Area or ProductionArea
        Input selection; results are not clipped to this boundary.
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

    Returns
    -------
    pathlib.Path
        Combined afwateringseenheden GeoPackage.
    """
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
    context = unary_union([box(*tile.bounds) for tile in tiles]).buffer(tile_buffer)
    with production_run(
        store.processed_data_dir,
        "afwateringseenheden",
        selected.value,
        run_id=run_id,
        resume=resume,
        overwrite=overwrite,
        parameters={
            "area": selected.identity,
            "crs": settings.crs,
            "tile_size_m": tile_size,
            "tile_buffer_m": tile_buffer,
            "burn_depth_m": 100,
            "max_fill_depth_m": 50,
            "random_seed": 12345,
            "authority_filter": False,
            "clip_to_area": False,
        },
    ) as run:
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
        ahn = prepare_ahn(store, context, run.path / "input" / "ahn.vrt", preparation)
        run.record_inputs({"ahn": ahn, "hydamo": hydamo, "landsgrens": boundary})
        hydro = read_hydroobjecten(hydamo, spatial_selection=context)
        primary = hydro.loc[
            hydro[CATEGORIE_OPPERVLAKTEWATER_COLUMN].eq("primair")
        ].copy()
        secondary = hydro.loc[
            hydro[CATEGORIE_OPPERVLAKTEWATER_COLUMN].eq("secundair")
        ].copy()
        points = read_puntobjecten(
            hydamo, layers=["gemaal", "stuw"], spatial_selection=context
        )
        network = prepare_watersysteem(primary, points, hydroobject_secundair=secondary)
        network_path = write_watersysteem(
            hydroobject_primair=primary,
            hydroobject_secundair=secondary,
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
        )
        if result.merged_path is None:
            raise ValueError("Geen afwateringseenheden geproduceerd voor dit gebied")
        logger.info("Afwateringseenheden voltooid: %s", result.merged_path)
        return result.merged_path
