import runpy
from pathlib import Path

import geopandas as gpd
import numpy as np
from geopandas.testing import assert_geodataframe_equal
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from waterlagen.functioneel_landgebruik.bag_panden_en_verblijfsobjecten import (
    read_bag_source_data,
)
from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import prepare_bag
from waterlagen.functioneel_landgebruik.landgebruikstabel import load_landuse_table
from waterlagen.functioneel_landgebruik.rasteriseren import rasterize_features


def test_production_matches_control_and_masks_unresolved_panden(tmp_path):
    path = tmp_path / "bag.gpkg"
    panden = gpd.GeoDataFrame(
        {"identificatie": ["shop", "open"], "status": ["Pand in gebruik"] * 2},
        geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10)],
        crs="EPSG:28992",
    )
    vbo = gpd.GeoDataFrame(
        {
            "identificatie": ["v1", "v2", "v3"],
            "pand_identificatie": ["shop", "shop", "open"],
            "gebruiksdoel": [
                "woonfunctie",
                "winkelfunctie",
                "onderwijsfunctie,sportfunctie",
            ],
            "oppervlakte": [150, 50, 200],
        },
        # One linked VBO is deliberately outside the selected bounds.
        geometry=[Point(100, 100), Point(5, 5), Point(15, 5)],
        crs=panden.crs,
    )
    panden.to_file(path, layer="pand", driver="GPKG")
    vbo.to_file(path, layer="verblijfsobject", driver="GPKG")
    bounds = (-1, -1, 21, 11)
    source = read_bag_source_data(path, bounds=bounds)
    script = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts/controle_bag_landgebruik.py")
    )
    control = script["_process_area"](source, "test", 5)
    production = prepare_bag(
        path,
        pand_layer="pand",
        verblijfsobject_layer="verblijfsobject",
        bounds=bounds,
        dike_area=box(-1, -1, 11, 11),
        include_details=True,
    )
    common = [column for column in production if column in control]
    assert_geodataframe_equal(production[common], control[common], check_dtype=False)
    assert production["code"].tolist() == [30, 0]
    raster = np.full((10, 20), 95, dtype="uint8")
    rasterize_features(raster, production, from_origin(0, 10, 1, 1))
    assert raster[5, 5] == 30
    assert raster[5, 15] == 0


def test_note_legend_has_distinct_building_road_and_water_codes():
    table = load_landuse_table()
    assert table.by_id("BAG-001").inside == 1
    assert table.by_id("BGT-001").inside == 70
    assert table.by_id("BGT-033").inside == 100
