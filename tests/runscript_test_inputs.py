"""Kleine lokale bronbestanden voor Run Maker-tests."""

import json
import shutil

import geopandas as gpd
from shapely.geometry import box

from waterlagen.functioneel_landgebruik.landgebruikstabel import DEFAULT_MAPPING_CSV


def make_input(folder, option):
    path = folder / (
        "Aa's "
        + option.flag
        + (option.file_pattern.removeprefix("*") if option.kind != "directory" else "")
    )
    if option.flag == "landuse-run":
        path.mkdir()
        (path / "tiles").mkdir()
        (path / "tiles/functioneel_landgebruik_test.tif").touch()
        (path / "tiles.gpkg").touch()
        (path / "landgebruik_met_code.csv").touch()
        (path / "run.json").write_text(
            json.dumps({"dataset": "functioneel_landgebruik", "status": "complete"})
        )
    elif option.flag == "mapping-csv":
        shutil.copyfile(DEFAULT_MAPPING_CSV, path)
    elif option.flag == "brandlagen-config":
        path.write_text(
            '[[lagen]]\npath="bron.gpkg"\nlayer="correcties"\n', encoding="utf-8"
        )
    elif option.flag == "ahn-vrt":
        path.write_text(
            '<VRTDataset rasterXSize="1" rasterYSize="1"><SRS>EPSG:28992</SRS>'
            '<VRTRasterBand dataType="Float32" band="1"/></VRTDataset>',
            encoding="utf-8",
        )
    else:
        if option.flag == "eigen-hydamo":
            layers = ["hydroobject", "gemaal", "stuw", "duikersifonhevel"]
        else:
            layers = [
                "bgt_waterdeel",
                "bgt_ondersteunendwaterdeel",
                "bgt_wegdeel",
                "bgt_ondersteunendwegdeel",
                "bgt_begroeidterreindeel",
                "bgt_onbegroeidterreindeel",
            ]
        frame = gpd.GeoDataFrame(geometry=[box(10, 10, 20, 20)], crs=28992)
        for layer in layers:
            frame.to_file(path, layer=layer)
    return path
