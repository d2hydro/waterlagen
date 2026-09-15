"""Prepare shared CBS and BAG VBO-buurt data for the inwoners workflow."""

from pathlib import Path

from waterlagen.administratieve_gebieden import download_wijk_buurtkaart_2025
from waterlagen.cbs import buurtgegevens_2025_path, download_buurtgegevens_2025
from waterlagen.datastore import DataStore
from waterlagen.logger import init_logger
from waterlagen.vbo_buurt import bouw_vbo_buurt


def main(data_store: DataStore | None = None) -> Path:
    """Download CBS sources and build shared BAG VBO and CBS buurt outputs."""
    data_store = data_store or DataStore()
    init_logger(
        name="inwoners",
        debug=False,
        log_file=data_store.data_dir / "inwoners.log",
    )
    buurtkaart = download_wijk_buurtkaart_2025(
        download_dir=data_store.administratieve_gebieden_dir,
        overwrite=False,
    )
    download_buurtgegevens_2025(
        download_dir=data_store.cbs_dir,
        overwrite=False,
    )
    result = bouw_vbo_buurt(
        bag_path=data_store.bag_dir / "bag-light.gpkg",
        buurtkaart_path=buurtkaart.target_path,
        cbs_buurtgegevens_path=buurtgegevens_2025_path(data_store.cbs_dir),
        bag_vbo_path=data_store.bag_vbo_path,
        cbs_buurt_path=data_store.cbs_buurt_path,
        overwrite=False,
    )
    return result.bag_vbo_path


if __name__ == "__main__":
    main()
