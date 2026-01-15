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


def get_bag_features(
    download_dir: Path,
    bbox: tuple[float, float, float, float],
    typenames: list[str] = [
        "bag:pand",
        "bag:verblijfsobject",
    ],
    crs: int = 28992,
) -> Path:
    """Download BAG for an extent via WFS

    Parameters
    ----------
    download_dir : Path
        Download dir to store GeoPackages
    typenames: list[str], optional
        List of WFS typenames (layers) to download. Default is ["bag:pand","bag:verblijfsobject"]
    bbox : tuple[float, float, float, float] | None, optional
        Extent with (xmin, ymin, xmax, ymax). BAG will be downloaded for this extent only.
    crs: int, optional
        Download CRS EPSG-code, by default 28992

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
    page_num = 1
    for typename in typenames:
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": typename,
            "srsName": f"EPSG:{crs}",
            "bbox": ",".join(map(str, (*bbox, f"EPSG:{crs}"))),
            "count": WFS_COUNT,
            "outputFormat": "application/json",
        }

        # init iter
        features = []
        start_index = 0
        features_sum = 0

        while True:
            # echo page number to console
            msg = f"Page: {page_num}"
            sys.stdout.write("\r" + msg)
            sys.stdout.flush()

            # request by start-index
            params["startIndex"] = start_index
            response = requests.get(url, params=params)
            response.raise_for_status()

            # read to GeoPackage
            gdf_page = gpd.read_file(io.BytesIO(response.content))

            if gdf_page.empty:
                break

            # append to list
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
            return gpd.GeoDataFrame(geometry=[], crs=crs)

        # concat features and set CRS
        gdf = gpd.pd.concat(features, ignore_index=True)
        gdf = gdf.set_crs(crs)

        for layer in set(gdf.id.str.split(".").str[0]):
            bag_gpkg = download_dir / f"bag_{layer}.gpkg"
            logger.info(f"writing {bag_gpkg}")
            mask = gdf.id.str.startswith(layer)
            gdf.loc[mask].to_file(bag_gpkg)

    return download_dir


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
