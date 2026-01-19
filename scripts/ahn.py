# %%
from pathlib import Path

from waterlagen import datastore
from waterlagen.ahn import get_ahn_rasters
from waterlagen.logger import init_logger

datastore.data_dir = Path(r"d:\projecten\D2602.HHNK\01_waterlagen\data")

logger = init_logger(
    name="ahn download", log_file=datastore.data_dir / "ahn_processing.log", debug=False
)

ahn_vrt = get_ahn_rasters(save_tiles_index=True)

# %% interpolate

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.fill import fillnodata
from rasterio.windows import Window, from_bounds
from rasterio.windows import transform as window_transform

from waterlagen.ahn.download import create_vrt_file

indices = [
    "M_04DN2",
    "M_04DZ2",
    "M_04GZ1",
    "M_09AZ2",
    "M_09BN1",
    "M_09BN2",
    "M_09BZ1",
    "M_09BZ2",
    "M_09CN2",
    "M_09CZ2",
    "M_09DN1",
    "M_09DN2",
    "M_09DZ1",
    "M_09DZ2",
    "M_09EN1",
    "M_09EZ1",
    "M_09HN2",
    "M_09HZ1",
    "M_09HZ2",
    "M_14AN2",
    "M_14AZ2",
    "M_14BN1",
    "M_14BN2",
    "M_14BZ1",
    "M_14BZ2",
    "M_14CN2",
    "M_14CZ1",
    "M_14CZ2",
    "M_14DN1",
    "M_14DN2",
    "M_14DZ1",
    "M_14DZ2",
    "M_14EN1",
    "M_14EN2",
    "M_14EZ1",
    "M_14EZ2",
    "M_14FN1",
    "M_14FZ1",
    "M_14FZ2",
    "M_14GN1",
    "M_14GN2",
    "M_14GZ1",
    "M_14GZ2",
    "M_14HN1",
    "M_14HN2",
    "M_14HZ1",
    "M_14HZ2",
    "M_15CZ1",
    "M_15CZ2",
    "M_18HZ2",
    "M_19AN1",
    "M_19AN2",
    "M_19AZ1",
    "M_19AZ2",
    "M_19BN1",
    "M_19BN2",
    "M_19BZ1",
    "M_19BZ2",
    "M_19CN1",
    "M_19CN2",
    "M_19CZ1",
    "M_19CZ2",
    "M_19DN1",
    "M_19DN2",
    "M_19DZ1",
    "M_19DZ2",
    "M_19EN1",
    "M_19EN2",
    "M_19EZ1",
    "M_19EZ2",
    "M_19FN1",
    "M_19FN2",
    "M_19FZ1",
    "M_19FZ2",
    "M_19GN1",
    "M_19GN2",
    "M_19GZ1",
    "M_19GZ2",
    "M_19HN1",
    "M_19HZ1",
    "M_19HZ2",
    "M_20AN1",
    "M_20AN2",
    "M_20AZ1",
    "M_20BN1",
    "M_24FN2",
    "M_24FZ2",
    "M_25AN1",
    "M_25AN2",
    "M_25AZ1",
    "M_25AZ2",
    "M_25BN1",
    "M_25BN2",
    "M_25BZ1",
    "M_25BZ2",
    "M_25CN1",
    "M_25CN2",
    "M_25DN1",
    "M_25DN2",
    "M_25EN1",
    "M_25EN2",
    "M_25EZ1",
    "M_25EZ2",
    "M_25FN1",
    "M_25FN2",
    "M_25FZ1",
    "M_25FZ2",
    "M_25GN1",
    "M_25GN2",
    "M_25HN1",
    "M_25HN2",
    "M_26AN1",
]
max_search_distance: float = 100
band: int = 1

tiles_gdf = gpd.read_file(ahn_vrt.with_suffix(".gpkg")).set_index("kaart_index")


# get and make destination dir
dst_dir = datastore.processed_data_dir.joinpath("ahn_filled")
logger.info(f"creating {dst_dir}")
dst_dir.mkdir(exist_ok=True, parents=True)

with rasterio.Env():
    with rasterio.open(ahn_vrt) as src:
        full = Window(col_off=0, row_off=0, width=src.width, height=src.height)
        nodata = src.nodata
        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            compress="deflate",
            predictor=2,
            tiled=True,
            dtype=np.int16,
        )
        scales = src.scales
        raster_cell_size = abs(src.res[0])

        # iter polygons
        for idx, index in enumerate(indices):
            logger.info(f"start interpolating {index} ({idx + 1}/{len(indices)})")
            geometry = tiles_gdf.at[index, "geometry"]

            # fill window by buffered polygon
            fill_window = from_bounds(
                *geometry.buffer(max_search_distance).bounds, transform=src.transform
            )
            fill_window = fill_window.intersection(
                Window(col_off=0, row_off=0, width=src.width, height=src.height)
            )

            if fill_window.width <= 0 or fill_window.height <= 0:
                raise ValueError(
                    "Resulting window is empty after clipping to dataset extent."
                )

            # read data
            fill_data = src.read(band, window=fill_window, masked=True)

            # fill nodata
            valid_mask = fill_data != nodata
            fill_data = fillnodata(
                fill_data,
                # mask=valid_mask,
                max_search_distance=max_search_distance,
            )

            # data window by polygon
            window = from_bounds(
                *geometry.bounds, transform=src.transform
            ).intersection(
                Window(col_off=0, row_off=0, width=src.width, height=src.height)
            )

            # Compute offsets of small window relative to big window.
            row0 = int(round(window.row_off - fill_window.row_off))
            col0 = int(round(window.col_off - fill_window.col_off))
            h = int(round(window.height))
            w = int(round(window.width))

            if (
                row0 < 0
                or col0 < 0
                or (row0 + h) > fill_data.shape[0]
                or (col0 + w) > fill_data.shape[1]
            ):
                raise ValueError(
                    "window is not fully contained within fill_window/data array."
                )

            # clip data to polygon window
            data = fill_data[row0 : row0 + h, col0 : col0 + w]
            transform = window_transform(window, src.transform)

            # write data to GeoTiff
            dst_file = dst_dir.joinpath(f"{index}.tif")
            logger.info(f"writing {dst_file}")
            # updating profile with size and transform
            profile.update(
                height=data.shape[0], width=data.shape[1], transform=transform
            )
            with rasterio.open(dst_file, "w", **profile) as dst:
                # writing data and scale if present
                dst.write(data, 1)
                dst.scales = scales

                # add overviews to 5m and 25m
                factors = [
                    int(size / raster_cell_size)
                    for size in [5, 25]
                    if size > raster_cell_size
                ]
                dst.build_overviews(factors, Resampling.average)
                dst.update_tags(ns="rio_overview", resampling="average")

create_vrt_file(dst_dir)
