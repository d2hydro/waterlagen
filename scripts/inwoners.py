"""Prepare shared CBS and BAG VBO-buurt data for the inwoners workflow."""

import argparse
from pathlib import Path
from time import perf_counter

from waterlagen._production import ProductionRun, add_run_arguments, production_run
from waterlagen.administratieve_gebieden import download_wijk_buurtkaart_2025
from waterlagen.cbs import buurtgegevens_2025_path, download_buurtgegevens_2025
from waterlagen.datastore import DataStore
from waterlagen.inwoners import bouw_inwoners
from waterlagen.logger import get_logger, init_logger
from waterlagen.settings import settings
from waterlagen.vbo_buurt import bouw_vbo_buurt

logger = get_logger(__name__)

WRITE_GEOPARQUET = True


def main(
    data_store: DataStore | None = None,
    *,
    write_geoparquet: bool = WRITE_GEOPARQUET,
    run_id: str | None = None,
    resume: bool = False,
    overwrite: bool = False,
) -> Path:
    """Produce inwoners per woon-VBO from CBS and BAG source data."""
    data_store = data_store or DataStore()
    with production_run(
        data_store.processed_data_dir,
        "inwoners",
        "nederland",
        run_id=run_id,
        resume=resume,
        overwrite=overwrite,
        parameters={
            "cbs_year": 2025,
            "crs": settings.crs,
            "write_geoparquet": write_geoparquet,
        },
    ) as run:
        return _produce(
            data_store, run, write_geoparquet=write_geoparquet, overwrite=overwrite
        )


def _produce(
    data_store: DataStore,
    run: ProductionRun,
    *,
    write_geoparquet: bool,
    overwrite: bool,
) -> Path:
    init_logger(
        name="inwoners",
        debug=False,
        log_file=run.path / "inwoners.log",
    )
    logger.info("Productie-uitvoermap: %s", run.path)
    started = perf_counter()
    buurtkaart = download_wijk_buurtkaart_2025(
        download_dir=data_store.administratieve_gebieden_dir,
        overwrite=False,
    )
    logger.info("CBS buurtkaart stap completed in %.1f s", perf_counter() - started)

    started = perf_counter()
    download_buurtgegevens_2025(
        download_dir=data_store.cbs_dir,
        overwrite=False,
    )
    logger.info("CBS buurtgegevens stap completed in %.1f s", perf_counter() - started)

    started = perf_counter()
    result = bouw_vbo_buurt(
        bag_path=data_store.bag_dir / "bag-light.gpkg",
        buurtkaart_path=buurtkaart.target_path,
        cbs_buurtgegevens_path=buurtgegevens_2025_path(data_store.cbs_dir),
        bag_vbo_path=data_store.bag_vbo_path,
        cbs_buurt_path=data_store.cbs_buurt_path,
        overwrite=False,
    )
    logger.info("VBO-buurt stap completed in %.1f s", perf_counter() - started)

    started = perf_counter()
    run.record_inputs(
        {
            "bag": data_store.bag_dir / "bag-light.gpkg",
            "buurtkaart": buurtkaart.target_path,
            "cbs_buurtgegevens": buurtgegevens_2025_path(data_store.cbs_dir),
            "bag_vbo": result.bag_vbo_path,
            "cbs_buurt": data_store.cbs_buurt_path,
        }
    )
    inwoners = bouw_inwoners(
        bag_vbo_path=result.bag_vbo_path,
        cbs_buurt_path=data_store.cbs_buurt_path,
        target_path=run.path / "inwoners.gpkg",
        overwrite=overwrite,
        geoparquet_path=run.path / "inwoners.parquet",
        write_geoparquet=write_geoparquet,
    )
    logger.info("Inwoners stap completed in %.1f s", perf_counter() - started)
    return inwoners.target_path


def cli() -> None:
    """Run production with shared output-folder options."""
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    add_run_arguments(parser)
    main(**vars(parser.parse_args()))


if __name__ == "__main__":
    cli()
