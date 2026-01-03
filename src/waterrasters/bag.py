import io
import logging
import sys
from pathlib import Path

import geopandas as gpd
import requests

logger = logging.getLogger(__name__)

ROOT_URL = "https://service.pdok.nl/lv/bag"
MAX_WFS_FEATURES = 50000
WFS_COUNT = 1000


def get_bag_panden(
    download_dir: Path,
    bbox: tuple[float, float, float, float],
) -> Path:
    """Download BAG for an extent via WFS

    Parameters
    ----------
    download_dir : Path
        Download dir to store GeoPackages
    bbox : tuple[float, float, float, float] | None, optional
        Extent with (xmin, ymin, xmax, ymax). BAG will be downloaded for this extent only.

    Returns
    -------
    Path
        Path to GeoPackage
    """

    # make dir
    download_dir = Path(download_dir)
    download_dir.mkdir(exist_ok=True, parents=True)

    # specify request url and params
    url = f"{ROOT_URL}/wfs/v2_0"
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "bag:pand",
        "srsName": "EPSG:28992",
        "bbox": ",".join(map(str, (*bbox, "EPSG:28992"))),
        "count": WFS_COUNT,
        "outputFormat": "application/json",
    }

    # init iter
    features = []
    start_index = 0
    page_num = 1
    features_sum = 0

    while True:
        logger.debug(f"page {page_num}")
        print(f"page {page_num}")
        params["startIndex"] = start_index
        r = requests.get(url, params=params)
        r.raise_for_status()

        gdf_page = gpd.read_file(io.BytesIO(r.content))

        if gdf_page.empty:
            break

        features.append(gdf_page)
        features_sum += len(gdf_page)
        if features_sum >= MAX_WFS_FEATURES:
            logger.warning(f"you can't request for more than {MAX_WFS_FEATURES}")
            break

        # next page
        start_index += len(gdf_page)
        page_num += 1
        if len(gdf_page) < WFS_COUNT:
            break

    if not features:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:28992")

    # concat and set CRS
    gdf = gpd.pd.concat(features, ignore_index=True)
    gdf = gdf.set_crs(28992)

    bag_pand_gpkg = download_dir / "bag_pand.gpkg"
    gdf.to_file(bag_pand_gpkg)

    return bag_pand_gpkg


def download_bag(download_dir: Path):
    """Download BAG for The Netherlands

    Parameters
    ----------
    download_dir : Path
        Download dir to store GeoPackages
    """
    # make dir to GPKG
    download_dir = Path(download_dir)
    download_dir.mkdir(exist_ok=True, parents=True)

    # define download params
    url = f"{ROOT_URL}/atom/downloads/bag-light.gpkg"
    chunk_size: int = 1024 * 1024
    bag_gpkg = download_dir / Path(url).name
    downloaded = 0

    # stream chuncks to output file
    with requests.get(url, stream=True, allow_redirects=True, timeout=30) as response:
        response.raise_for_status()

        # get file-size for logging
        total = response.headers.get("Content-Length")
        total = int(total) if total is not None else None

        # open GPKG for chunked writing
        with open(bag_gpkg, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    # write chunck
                    f.write(chunk)

                    # echo progress in console
                    downloaded += len(chunk)
                    if total is not None:
                        percent = downloaded / total * 100
                        msg = f"{downloaded / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB ({percent:.1f}%)"
                    else:
                        msg = f"{downloaded / 1024 / 1024:.1f} MB"
                    sys.stdout.write("\r" + msg)
                    sys.stdout.flush()
