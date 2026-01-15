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
    bbox: tuple[float, float, float, float],
    type_names: list[str] = [
        "bag:pand",
        "bag:verblijfsobject",
    ],
    crs: int = 28992,
) -> gpd.GeoDataFrame:
    """Download BAG for an extent via WFS to a GeoDataFrame

    Parameters
    ----------
    download_dir : Path
        Download dir to store GeoPackages
    type_names: list[str], optional
        List of WFS type_names (layers) to download. Default is ["bag:pand","bag:verblijfsobject"]
    bbox : tuple[float, float, float, float] | None, optional
        Extent with (xmin, ymin, xmax, ymax). BAG will be downloaded for this extent only.
    crs: int, optional
        Download CRS EPSG-code, by default 28992

    Returns
    -------
    GeoDataFrame
        GeoDataFrame with BAG features
    """

    # specify request url and params
    url = f"{ROOT_URL}/wfs/v2_0"
    page_num = 1
    for type_name in type_names:
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": type_name,
            "srsName": f"EPSG:{crs}",
            "bbox": ",".join(map(str, (*bbox, f"EPSG:{crs}"))),
            "count": WFS_COUNT,
            "outputFormat": "application/json",
        }

        # init iter
        features = []
        start_index = 0
        features_sum = 0
        logger.info(
            "Start downloading BAG using WFS, {WFS_COUNT} features per page (download)"
        )
        while True:
            # echo page number to console
            msg = f"Downloading WFS page: {page_num:02d}"
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
                logger.warning(
                    f"Your download is incomplete!. Requested features more than {MAX_WFS_FEATURES}. Use a smaller bbox of use `download_bag_nl()` to download BAG for The Netherlands"
                )
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

    return gdf


def download_bag_nl(download_dir: Path, overwrite: bool = True) -> Path:
    """Download BAG for The Netherlands

    Parameters
    ----------
    download_dir : Path
        Download dir to store GeoPackages
    overwrite : bool, optional
        If not True BAG will only be downloaded if not existing. Default is True

    Returns
    -------
    Path
        Path to BAG GeoPackage
    """
    # make dir to GPKG
    download_dir = Path(download_dir)
    download_dir.mkdir(exist_ok=True, parents=True)

    # define download params
    url = f"{ROOT_URL}/atom/downloads/bag-light.gpkg"
    chunk_size: int = 1024 * 1024
    bag_gpkg = download_dir / Path(url).name
    if (not bag_gpkg.exists()) or overwrite:
        downloaded = 0

        # stream chuncks to output file
        logger.info("Start downloading BAG {url} to {bag_gpkg}")
        with requests.get(
            url, stream=True, allow_redirects=True, timeout=30
        ) as response:
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

    return bag_gpkg
