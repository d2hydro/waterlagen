"""Prepare shared CBS and BAG VBO-buurt data for the inwoners workflow."""

from pathlib import Path
from time import perf_counter

from waterlagen.administratieve_gebieden import download_wijk_buurtkaart_2025
from waterlagen.cbs import buurtgegevens_2025_path, download_buurtgegevens_2025
from waterlagen.datastore import DataStore
from waterlagen.inwoners import bouw_inwoners
from waterlagen.logger import get_logger, init_logger
from waterlagen.vbo_buurt import bouw_vbo_buurt

logger = get_logger(__name__)

WRITE_GEOPARQUET = True


def main(
    data_store: DataStore | None = None,
    *,
    write_geoparquet: bool = WRITE_GEOPARQUET,
) -> Path:
    """Produce inwoners per woon-VBO from CBS and BAG source data."""
    data_store = data_store or DataStore()
    init_logger(
        name="inwoners",
        debug=False,
        log_file=data_store.data_dir / "inwoners.log",
    )
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
    inwoners = bouw_inwoners(
        bag_vbo_path=result.bag_vbo_path,
        cbs_buurt_path=data_store.cbs_buurt_path,
        target_path=data_store.inwoners_path,
        overwrite=False,
        geoparquet_path=data_store.inwoners_parquet_path,
        write_geoparquet=write_geoparquet,
    )
    logger.info("Inwoners stap completed in %.1f s", perf_counter() - started)
    return inwoners.target_path


if __name__ == "__main__":
    main(write_geoparquet=WRITE_GEOPARQUET)
