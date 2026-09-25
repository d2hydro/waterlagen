import logging

import geopandas as gpd
import pytest
from shapely.geometry import Point

from waterlagen.functioneel_landgebruik import parallel
from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import _assign_source_codes
from waterlagen.functioneel_landgebruik.landgebruik_berekenen import (
    FunctioneelLandgebruikLayers,
    FunctioneelLandgebruikSources,
)
from waterlagen.raster.config import RasterOutputConfig


@pytest.mark.parametrize("fails", [False, True])
def test_worker_logs_details_to_file_and_restores_logger(
    tmp_path, monkeypatch, capsys, fails
):
    def build(**kwargs):
        data = gpd.GeoDataFrame(
            {"type": ["bouwland", "bouwland", "fruitteelt"]},
            geometry=[Point(0, 0)] * 3,
            crs="EPSG:28992",
        )
        _assign_source_codes(
            data, {}, field="type", dike_area=None, source_layer="bgt_terrein"
        )
        if fails:
            raise ValueError("testfout")
        return kwargs["target_path"]

    monkeypatch.setattr(parallel, "bouw_functioneel_landgebruik", build)
    job = parallel.FunctioneelLandgebruikTileJob(
        tile_id="test",
        bounds=(0, 0, 1, 1),
        target_path=tmp_path / "test.tif",
        overwrite=False,
        resolution_m=0.5,
        crs="EPSG:28992",
        sources=FunctioneelLandgebruikSources(),
        layers=FunctioneelLandgebruikLayers(),
        output_config=RasterOutputConfig(),
    )
    logger = logging.getLogger("waterlagen")
    original = (logger.handlers[:], logger.level, logger.propagate)
    if fails:
        with pytest.raises(ValueError, match="testfout"):
            parallel._build_tile_worker(job)
    else:
        assert parallel._build_tile_worker(job) == job.target_path
    assert (logger.handlers, logger.level, logger.propagate) == original
    console = capsys.readouterr()
    assert "CSV-indeling" not in console.err + console.out
    log = (tmp_path / "logs" / "test.log").read_text(encoding="utf-8")
    assert "Start tegel test" in log
    assert "laag=bgt_terrein; veld=type; 3 van 3" in log
    assert "'bouwland': 2" in log
    assert "'fruitteelt': 1" in log
    assert ("mislukt" if fails else "gereed in") in log
