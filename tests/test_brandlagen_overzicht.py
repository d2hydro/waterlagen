"""The QGIS overview preserves input and is replaced as one complete file."""

import geopandas as gpd
import pyogrio
import pytest
from shapely.geometry import LineString, box

from waterlagen.afwateringseenheden import brandlagen_overzicht as module
from waterlagen.afwateringseenheden.sources import WatersysteemSources


def test_overview_preserves_sources_and_removes_stale_layers(tmp_path, monkeypatch):
    lines = gpd.GeoDataFrame(
        {"bron_id": ["original"]}, geometry=[LineString([(0, 0), (10, 10)])], crs=28992
    )
    sources = WatersysteemSources(lines, lines.iloc[:0], lines, lines.iloc[:0])
    optional = gpd.GeoDataFrame(
        {
            "broncode": [3, 4],
            "bronlaag": ["bgt_waterdeel", "bgt_waterdeel"],
            "brandwaarde": [-10.0, -5.0],
            "prioriteit": [2, 1],
        },
        geometry=[box(0, 0, 1, 1), box(2, 2, 3, 3)],
        crs=28992,
    )
    path = tmp_path / "brandlagen.gpkg"
    module._write_brandlagen_overzicht(sources, optional, path)
    assert set(pyogrio.list_layers(path)[:, 0]) == {
        "hydamo_primair",
        "hydamo_secundair",
        "bgt_waterdeel",
        "bron_4_bgt_waterdeel",
    }
    actual = gpd.read_file(path, layer="bgt_waterdeel")
    assert actual.brandwaarde.tolist() == [-10.0]
    assert actual.geometry.iloc[0].equals(optional.geometry.iloc[0])
    assert actual.crs.to_epsg() == 28992
    assert gpd.read_file(path, layer="hydamo_primair").bron_id.tolist() == ["original"]
    assert gpd.read_file(path, layer="hydamo_secundair").empty

    module._write_brandlagen_overzicht(sources, optional.iloc[:0], path)
    assert set(pyogrio.list_layers(path)[:, 0]) == {
        "hydamo_primair",
        "hydamo_secundair",
    }
    previous = path.read_bytes()

    def fail(*args, **kwargs):
        raise ValueError("validation failed")

    monkeypatch.setattr(module, "validate_geopackage", fail)
    with pytest.raises(ValueError, match="validation failed"):
        module._write_brandlagen_overzicht(sources, optional, path)
    assert path.read_bytes() == previous
