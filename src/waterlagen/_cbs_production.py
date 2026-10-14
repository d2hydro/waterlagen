"""Shared source preparation and area context for inwoners and personenauto's."""

from pathlib import Path
from typing import Literal

from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._geopandas import read_file
from waterlagen._production import production_run, validate_run_target
from waterlagen._sources import SourcePreparation, prepare_cached, source_options
from waterlagen.administratieve_gebieden import download_wijk_buurtkaart_2025
from waterlagen.administratieve_gebieden.download import wijk_buurtkaart_2025_path
from waterlagen.areas import Area, ProductionArea, area_name, resolve_area
from waterlagen.bag import download_bag_light
from waterlagen.cbs import buurtgegevens_2025_path, download_buurtgegevens_2025
from waterlagen.datastore import DataStore
from waterlagen.settings import settings
from waterlagen.vbo_buurt import bouw_vbo_buurt
from waterlagen.vbo_buurt.build import BAG_VBO_LAYER, CBS_BUURT_OUTPUT_LAYER


def select_buurt_context(
    bag_path: Path, buurt_path: Path, area: ProductionArea, target_dir: Path
) -> tuple[Path, Path]:
    """Retain complete intersecting CBS buurten, including all their woon-VBOs."""
    buurten = read_file(buurt_path, layer=CBS_BUURT_OUTPUT_LAYER)
    from waterlagen._crs import same_crs

    if not same_crs(buurten.crs, area.crs):
        raise ValueError("CBS-buurt-CRS verschilt van gebieds-CRS")
    selected = buurten.loc[
        buurten.intersects(area.geometry) & ~buurten.touches(area.geometry)
    ]
    if selected.empty:
        raise ValueError(f"Geen CBS-buurten in {area.value}")
    bag = read_file(bag_path, layer=BAG_VBO_LAYER)
    bag = bag.loc[bag.buurtcode.isin(selected.buurtcode)]
    target_dir.mkdir(parents=True, exist_ok=True)
    bag_target, buurt_target = (
        target_dir / "bag_vbo.gpkg",
        target_dir / "cbs_buurt.gpkg",
    )
    if not bag_target.exists():
        write_geopackage_layer_atomically(bag, bag_target, layer_name=BAG_VBO_LAYER)
    if not buurt_target.exists():
        write_geopackage_layer_atomically(
            selected, buurt_target, layer_name=CBS_BUURT_OUTPUT_LAYER
        )
    return bag_target, buurt_target


def produce(
    dataset: Literal["autos", "inwoners"],
    data_store: DataStore | None = None,
    *,
    area: str | Area | ProductionArea = Area.nederland,
    write_geoparquet: bool = True,
    run_id: str | None = None,
    resume: bool = False,
    overwrite: bool = False,
    refresh_sources: bool = False,
    offline: bool = False,
    preparation: SourcePreparation | None = None,
) -> Path:
    """Produce a CBS distribution using complete buurt context and explicit caching."""
    from waterlagen.autos import bouw_autos
    from waterlagen.inwoners import bouw_inwoners

    store = data_store or DataStore()
    validate_run_target(
        store.processed_data_dir,
        dataset,
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
    selected_area = resolve_area(area, store, preparation)
    with production_run(
        store.processed_data_dir,
        dataset,
        selected_area.value,
        run_id=run_id,
        resume=resume,
        overwrite=overwrite,
        parameters={
            "area": selected_area.identity,
            "cbs_year": 2025,
            "crs": settings.crs,
            "write_geoparquet": write_geoparquet,
        },
    ) as run:
        bag = store.bag_dir / "bag-light.gpkg"
        buurt = wijk_buurtkaart_2025_path(
            download_dir=store.administratieve_gebieden_dir
        )
        cbs = buurtgegevens_2025_path(store.cbs_dir)
        preparation.ensure(
            bag,
            lambda: download_bag_light(
                download_dir=store.bag_dir, overwrite=preparation.refresh
            ),
        )
        preparation.ensure(
            buurt,
            lambda: download_wijk_buurtkaart_2025(
                download_dir=store.administratieve_gebieden_dir,
                overwrite=preparation.refresh,
                progress=False,
            ),
        )
        preparation.ensure(
            cbs,
            lambda: download_buurtgegevens_2025(
                download_dir=store.cbs_dir, overwrite=preparation.refresh
            ),
        )
        inputs = {"bag": bag, "buurtkaart": buurt, "cbs": cbs}
        run.record_inputs(inputs)
        # A missing companion invalidates the complete shared preparation.
        if not store.cbs_buurt_path.exists():
            manifest = store.bag_vbo_path.with_name(
                store.bag_vbo_path.name + ".inputs.json"
            )
            manifest.unlink(missing_ok=True)
        prepare_cached(
            store.bag_vbo_path,
            inputs,
            lambda: bouw_vbo_buurt(
                bag_path=bag,
                buurtkaart_path=buurt,
                cbs_buurtgegevens_path=cbs,
                bag_vbo_path=store.bag_vbo_path,
                cbs_buurt_path=store.cbs_buurt_path,
                overwrite=True,
            ),
        )
        bag_vbo, cbs_buurt = store.bag_vbo_path, store.cbs_buurt_path
        if selected_area.value != "nederland":
            bag_vbo, cbs_buurt = select_buurt_context(
                bag_vbo, cbs_buurt, selected_area, run.path / "input"
            )
        kwargs = {
            "bag_vbo_path": bag_vbo,
            "cbs_buurt_path": cbs_buurt,
            "target_path": run.path / f"{dataset}.gpkg",
            "overwrite": overwrite,
            "geoparquet_path": run.path / f"{dataset}.parquet",
            "write_geoparquet": write_geoparquet,
        }
        if dataset == "autos":
            return bouw_autos(**kwargs, cbs_buurtgegevens_path=cbs).target_path
        return bouw_inwoners(**kwargs).target_path
