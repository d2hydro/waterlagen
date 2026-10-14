"""Prepare every source required by a complete land-use production."""

from pathlib import Path

from waterlagen._sources import SourcePreparation, prepare_cached
from waterlagen.areas import ensure_land_boundary
from waterlagen.bag import download_bag_light
from waterlagen.bgt.download import (
    BGT_PREDEFINED_URL,
    DEFAULT_PREDEFINED_ARCHIVE,
    _download_validated_zip_archive,
)
from waterlagen.bgt.productie import main as prepare_bgt
from waterlagen.brp import download_brp
from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik.landgebruik_berekenen import (
    FunctioneelLandgebruikSources,
)
from waterlagen.functioneel_landgebruik.osm_drinkwater import download_osm_drinkwater
from waterlagen.hydamo import download_hydamo
from waterlagen.liwo import FILENAME, download_raster, polygonize_selected
from waterlagen.top10nl import download_top10nl
from waterlagen.waterketen_damo import download_waterketen_damo


def prepare_sources(
    store: DataStore,
    preparation: SourcePreparation,
    *,
    bgt_path: Path | None = None,
    workers: int = 1,
) -> FunctioneelLandgebruikSources:
    """Prepare the standard sources; never silently omit optional cached datasets."""
    ensure_land_boundary(store, preparation)
    paths = FunctioneelLandgebruikSources.from_datastore(store)
    preparation.ensure(
        paths.bag_gpkg,
        lambda: download_bag_light(
            download_dir=store.bag_dir, overwrite=preparation.refresh
        ),
    )
    preparation.ensure(
        paths.brp_gpkg,
        lambda: download_brp(
            download_dir=store.brp_dir,
            filename=paths.brp_gpkg.name,
            overwrite=preparation.refresh,
        ),
    )
    preparation.ensure(
        paths.top10nl_gpkg,
        lambda: download_top10nl(
            download_dir=store.top10nl_dir, overwrite=preparation.refresh
        ),
    )
    if bgt_path is None:
        archive = store.bgt_dir / DEFAULT_PREDEFINED_ARCHIVE
        # An existing prepared BGT is sufficient until a source refresh is requested.
        if preparation.refresh or archive.exists() or not paths.bgt_gpkg.exists():
            preparation.ensure(
                archive,
                lambda: _download_validated_zip_archive(
                    url=BGT_PREDEFINED_URL,
                    archive_path=archive,
                    description=archive.name,
                    chunk_size=1024 * 1024,
                    timeout=300,
                    progress=False,
                ),
            )
            prepare_cached(
                paths.bgt_gpkg,
                {"archive": archive},
                lambda: prepare_bgt(store, overwrite=True, workers=workers),
            )
    elif not Path(bgt_path).is_file():
        raise FileNotFoundError(f"Opgegeven BGT-bestand ontbreekt: {bgt_path}")
    raster = store.source_data_dir / "liwo" / FILENAME
    if preparation.refresh or raster.exists() or not paths.buitendijks_gpkg.exists():
        preparation.ensure(
            raster,
            lambda: download_raster(
                raster, overwrite=preparation.refresh, progress=False
            ),
        )
        prepare_cached(
            paths.buitendijks_gpkg,
            {"raster": raster},
            lambda: polygonize_selected(raster, paths.buitendijks_gpkg),
        )
    hydamo = store.source_data_dir / "hydamo" / "hydamo.gpkg"
    preparation.ensure(
        hydamo,
        lambda: download_hydamo(
            download_dir=hydamo.parent, overwrite=preparation.refresh, progress=False
        ),
    )
    rwzi = store.source_data_dir / "waterketen_damo" / "waterketen_damo.gpkg"
    preparation.ensure(
        rwzi,
        lambda: download_waterketen_damo(
            target_path=rwzi, overwrite=preparation.refresh, progress=False
        ),
    )
    drinking = store.source_data_dir / "osm" / "drinkwaterlocaties.gpkg"
    preparation.ensure(
        drinking,
        lambda: download_osm_drinkwater(
            target_path=drinking, data_store=store, overwrite=preparation.refresh
        ),
    )
    from dataclasses import replace

    return replace(
        FunctioneelLandgebruikSources.from_datastore(store),
        bgt_gpkg=Path(bgt_path) if bgt_path else paths.bgt_gpkg,
    )
