# %%
import io

import geopandas as gpd
import requests

WFS_URL = "https://service.pdok.nl/lv/bag/wfs/v2_0"


def bag_panden_bbox_wfs(bbox, count=1000, max_features=None):
    """
    bbox: (minx, miny, maxx, maxy) in EPSG:28992
    """
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "bag:pand",
        "srsName": "EPSG:28992",
        "bbox": ",".join(map(str, (*bbox, "EPSG:28992"))),
        "count": count,
        "outputFormat": "application/json",
    }

    features = []
    start_index = 0

    while True:
        params["startIndex"] = start_index
        r = requests.get(WFS_URL, params=params)
        r.raise_for_status()

        gdf_page = gpd.read_file(io.BytesIO(r.content))

        if gdf_page.empty:
            break

        features.append(gdf_page)

        if max_features and sum(len(f) for f in features) >= max_features:
            break

        # volgende pagina
        start_index += len(gdf_page)
        if len(gdf_page) < count:
            break

    if not features:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:28992")

    gdf = gpd.pd.concat(features, ignore_index=True)
    gdf = gdf.set_crs("EPSG:28992")
    return gdf
