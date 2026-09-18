"""Download the shared BAG-light input for production workflows."""

from pathlib import Path

from waterlagen.bag import download_bag_light
from waterlagen.datastore import DataStore
from waterlagen.logger import init_logger


def main(data_store: DataStore | None = None) -> Path:
    """Download BAG-light once, reusing an existing valid download."""
    data_store = data_store or DataStore()
    logger = init_logger(
        name="BAG_download", log_file=data_store.data_dir / "get_bag.log"
    )
    logger.info("BAG downloaden naar %s", data_store.bag_dir)
    return download_bag_light(download_dir=data_store.bag_dir, overwrite=False)


if __name__ == "__main__":
    main()
