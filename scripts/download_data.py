# %%
from waterlagen import settings
from waterlagen.ahn import create_download_dir, get_ahn_rasters, get_tiles_gdf
from waterlagen.ahn.api_config import AHNService
from waterlagen.bag import download_bag, get_bag_features
from waterlagen.bgt import get_bgt_features

# %% [markdown]
#
# ## Download AHN. Je kunt de volgende settings aanpassen
# - `download_dir`: sub-dir van settings.source_data die je kunt overrulen SOURCE_DATA in een .env file
# - `select_indices`: kaartbladen die je wilt selecteren
# - `model`: dtm of dsm
# - `ahn_version`: 3 t/m 6
# - `service`: ahn_pdok (https://service.pdok.nl/rws/ahn/atom/index.xml) of ahn_datastroom (https://www.ahn.nl)
# - `missing_only`: met True worden alleen missende tegels gedownload
# - `create_vrt`: hiermee wordt er een VRT-file bij geplaatst
# - `save_tiles_index`: met True wordt een GPKG met kaartindices geschreven

cell_size = "05"
model = "dtm"
ahn_version = 5
ahn_indices = ["M_19BZ1"]
missing_only = True


ahn_download_dir = create_download_dir(
    root_dir=settings.ahn_dir,
    model=model,
    cell_size=cell_size,
    ahn_version=ahn_version,
)

get_ahn_rasters(
    download_dir=ahn_download_dir,
    select_indices=ahn_indices,
    model=model,
    service="ahn_datastroom",
    ahn_version=ahn_version,
    cell_size=cell_size,
    missing_only=missing_only,
    create_vrt=True,
    save_tiles_index=True,
)


# %% [markdown]
#
# ## Download BGT
# Specificeer (BGT) `featuretypes`. Deze worden weggeschreven naar GeoPackages in download_dir
# We gebruiken hier de extent van de gedownloade AHN-tegel(s) als mask

poly_mask = get_tiles_gdf(
    ahn_service=AHNService(service="ahn_datastroom"), select_indices=ahn_indices
).union_all()
bgt_dir = get_bgt_features(
    featuretypes=["waterdeel", "wegdeel", "pand"],
    poly_mask=poly_mask,
    download_dir=settings.bgt_dir,
)

# %% [markdown]
#
# ## Download BAG
# Specificeer bounding-box op basis van poly_mask


DOWNLOAD_BAG_NL = False

bag_dir = get_bag_features(
    download_dir=settings.bag_dir,
    bbox=poly_mask.bounds,
    typenames=["bag:verblijfsobject", "bag:pand"],
)
if DOWNLOAD_BAG_NL:
    bag_gpkg = download_bag(bag_dir=settings.bag_dir)

# %%


import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.io import DatasetReader
from rasterio.mask import mask
from shapely.geometry import Polygon, mapping

dem_raster = ahn_download_dir / "AHN5_DTM_05m.vrt"
bag_gpkg = bag_dir / "bag_pand.gpkg"
bag_gdf = gpd.read_file(bag_gpkg, fid_as_index=True)
bag_pand_tif = bag_gpkg.with_name("pand_elev.tif")
print(bag_pand_tif)
# %%
buffer_step_m = 1
band = 1


def sample_polygon(
    polygon: Polygon, raster_src: DatasetReader, percentile: int = 75, band: int = 1
) -> int:
    """Sample raster over polygon

    Parameters
    ----------
    polygon : Polygon
        Input polygon
    raster_src : DatasetReader
        Opened rasterio DatasetReader
    percentile : int, optional
        Percentile-value to find, by default 75
    band : int, optional
        Raster-band, by default 1

    Returns
    -------
    int
        Raster sample value
    """
    nodata = raster_src.nodata

    data, _ = mask(
        raster_src, [polygon], crop=True, filled=True, nodata=nodata, indexes=band
    )

    if nodata is not None:
        data = data[data != nodata]

    if data.size:
        value = np.percentile(data, percentile).astype(data.dtype)
    else:
        value = None

    return value


def buffered_elevation_search(
    polygon: Polygon,
    raster_src: DatasetReader,
    buffer_step_m: float = 1,
    percentile: int = 75,
    band: int = 1,
    max_iters: int = 20,
):
    """Buffer iteratively and find elevation percentile of surrounding raster cells

    Parameters
    ----------
    polygon : Polygon
        Initial polygon
    raster_src : DatasetReader
        Opened rasterio DatasetReader
    buffer_step_m : float, optional
        Buffer increment to find values, by default 1
    percentile : int, optional
        Percentile-value to find, by default 75
    elevation_offset: float, optional
        Elevation offset above elevation found from
    band : int, optional
        Raster-band, by default 1
    max_iters : int, optional
        Max iters to buffer. If exceeded function will return None, by default 20

    Returns
    -------
    _type_
        _description_
    """
    for _ in range(max_iters):
        polygon = polygon.buffer(buffer_step_m)
        value = sample_polygon(
            polygon=polygon, raster_src=raster_src, percentile=percentile, band=band
        )
        if value is not None:
            return value


elevation_offset: float = 5

with rasterio.open(dem_raster) as raster_src:
    bag_gdf["vloerpeil"] = [
        buffered_elevation_search(
            polygon=geom, raster_src=raster_src, buffer_step_m=buffer_step_m
        )
        for geom in bag_gdf.geometry
    ]

    shapes = (
        (mapping(geom), int(val))
        for geom, val in zip(bag_gdf.geometry, bag_gdf["vloerpeil"] + elevation_offset)
    )

    profile = raster_src.profile
    profile["driver"] = "GTiff"
    with rasterio.open(bag_pand_tif, mode="w", **profile) as dst:
        data = rasterize(
            shapes=shapes,
            out_shape=raster_src.shape,
            transform=raster_src.transform,
            fill=raster_src.nodata,
            dtype=raster_src.profile["dtype"],
            all_touched=False,
        )
        dst.scales = raster_src.scales
        dst.write(data, band)


