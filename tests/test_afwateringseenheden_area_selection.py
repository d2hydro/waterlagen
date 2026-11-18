"""Eigen gebieden bereiken de bronvoorbereiding zonder waterschapsnaam."""

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from waterlagen import areas
from waterlagen.afwateringseenheden import productie
from waterlagen.datastore import DataStore


@pytest.mark.parametrize("selection", ["polygon", "rectangle", "12", "12,13"])
def test_area_selection_reaches_source_preparation(selection, tmp_path, monkeypatch):
    geometry = Polygon([(105000, 510000), (105100, 510000), (105050, 510100)])
    if selection == "polygon":
        path = tmp_path / "gebied.gpkg"
        gpd.GeoDataFrame(geometry=[geometry], crs=28992).to_file(path, layer="gebied")
        area = areas.area_from_file(path, layer="gebied")
        expected_code = None
    elif selection == "rectangle":
        area = areas.area_from_bounds(geometry.bounds)
        expected_code = None
    else:
        area = selection
        expected_code = selection

    class SourcesReached(Exception):
        pass

    original_validate = productie.validate_authority_options

    def validate(code, *args):
        assert code == expected_code
        original_validate(code, *args)

    def prepare(config, store, context, preparation, **kwargs):
        assert context.covers(geometry)
        raise SourcesReached

    monkeypatch.setattr(productie, "validate_authority_options", validate)
    monkeypatch.setattr(productie, "require_pcraster", lambda: None)
    monkeypatch.setattr(productie, "prepare_brand_sources", prepare)
    if isinstance(area, str):
        monkeypatch.setattr(
            productie,
            "resolve_area",
            lambda *args: areas.ProductionArea(
                areas.area_name(area), geometry, "EPSG:28992"
            ),
        )
    with pytest.raises(SourcesReached):
        productie.main(
            data_store=DataStore(data_dir=tmp_path / "data", _env_file=None),
            area=area,
            run_id="gebied-test",
            workers=1,
        )
