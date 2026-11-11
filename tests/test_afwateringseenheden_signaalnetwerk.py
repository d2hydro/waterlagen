"""Only actually applied, connected culverts enter the exclusion buffer."""

import json

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString

from waterlagen.afwateringseenheden._signaalnetwerk import read_used_network
from waterlagen.settings import settings


def write_raster(path, arrays, *, transform=None, tags=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.stack(arrays).astype("int32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[2],
        height=data.shape[1],
        count=len(arrays),
        dtype="int32",
        nodata=-999,
        crs=settings.crs,
        transform=transform or from_origin(0, 6, 1, 1),
    ) as target:
        target.write(data)
        if tags:
            target.update_tags(**tags)


@pytest.mark.parametrize(
    "treatment, applied, expected", [(2, 5, 1), (3, 5, 0), (2, 0, 0)]
)
def test_only_applied_and_connected_culverts_enter_buffer(
    tmp_path, treatment, applied, expected
):
    (tmp_path / "berekening/tegels/core").mkdir(parents=True)
    signals = gpd.GeoDataFrame(
        geometry=[LineString([(0.5, 1.5), (5.5, 1.5)])], crs=settings.crs
    )
    empty = signals.iloc[:0].copy()
    empty.to_file(tmp_path / "watersysteem.gpkg", layer="hydroobject_secundair")
    gpd.GeoDataFrame(
        {"bron_id": ["culvert"], "broncode": [3], "behandeling": ["aanvoer"]},
        geometry=[LineString([(1.5, 1.5), (4.5, 1.5)])],
        crs=settings.crs,
    ).to_file(tmp_path / "controle.gpkg", layer="duikers_waternet")
    network = tmp_path / "berekening/waterlopen_duikers/test.tif"
    write_raster(network, [np.full((6, 6), treatment), np.full((6, 6), 3)])
    audit = {
        "waternet": {"path": str(network)},
        "objects": {"culvert": {"toegepast": applied}},
    }
    (tmp_path / "berekening/tegels/core/duiker_inbranding.json").write_text(
        json.dumps(audit)
    )
    assert len(read_used_network(tmp_path, empty, signals)) == expected
