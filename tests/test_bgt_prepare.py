import json
import runpy
import zipfile
from pathlib import Path

import pyogrio
import pytest

from waterlagen.bgt.prepare import (
    SURFACE_LAYERS,
    combine_surface_layers,
    prepare_surface_layer,
    validate_surface_file,
)
from waterlagen.datastore import DataStore


def test_script_reuses_validated_gpkg_without_archive(tmp_path):
    import geopandas as gpd
    from shapely.geometry import MultiPolygon, box

    store = DataStore(data_dir=tmp_path)
    store.bgt_dir.mkdir(parents=True, exist_ok=True)
    target = store.bgt_dir / "bgt.gpkg"
    data = gpd.GeoDataFrame(geometry=[MultiPolygon([box(0, 0, 10, 10)])], crs=28992)
    pyogrio.write_dataframe(
        data, target, layer="bgt_waterdeel", layer_options={"GEOMETRY_NAME": "geom"}
    )
    status = {
        "status": "Gereed",
        "lagen": {
            name: "Overgeslagen: geen actuele vlakken" for name in SURFACE_LAYERS
        },
    }
    status["lagen"]["waterdeel"] = "Gereed"
    (store.bgt_dir / "bgt_actuele_vlakken.status.json").write_text(
        json.dumps(status), encoding="utf-8"
    )
    script = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts/bgt_actuele_vlakken.py")
    )
    before = target.read_bytes()
    script["main"](store)
    assert target.read_bytes() == before
    assert list(store.bgt_dir.glob("*.gpkg")) == [target]


def test_combine_preserves_layers_attributes_and_indexes(tmp_path):
    import geopandas as gpd
    from shapely.geometry import MultiPolygon, box

    paths = []
    for name in ("waterdeel", "wegdeel"):
        layer = f"bgt_{name}"
        path = tmp_path / f"{layer}.gpkg"
        data = gpd.GeoDataFrame(
            {"naam": [name]}, geometry=[MultiPolygon([box(0, 0, 10, 10)])], crs=28992
        )
        pyogrio.write_dataframe(
            data, path, layer=layer, layer_options={"GEOMETRY_NAME": "geom"}
        )
        paths.append(path)
    target = tmp_path / "samen.gpkg"
    combine_surface_layers(paths, target)
    assert set(pyogrio.list_layers(target)[:, 0]) == {"bgt_waterdeel", "bgt_wegdeel"}
    for path in paths:
        assert validate_surface_file(target, path.stem) == 1
        assert pyogrio.read_dataframe(target, layer=path.stem).naam.tolist() == [
            path.stem.removeprefix("bgt_")
        ]
    # Een mislukte nieuwe samenvoeging laat de bestaande uitvoer intact.
    before = target.read_bytes()
    with pytest.raises(ValueError, match="Geen actuele"):
        combine_surface_layers([], target)
    assert target.read_bytes() == before


def test_current_surfaces_preserve_polygon_not_kruinlijn(tmp_path):
    polygon = "<b:geometrie2d><gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>0 0 10 0 10 10 0 10 0 0</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon></b:geometrie2d>"
    line = "<b:kruinlijn><gml:LineString><gml:posList>0 0 10 10</gml:posList></gml:LineString></b:kruinlijn>"
    point = (
        "<b:geometrie2d><gml:Point><gml:pos>5 5</gml:pos></gml:Point></b:geometrie2d>"
    )
    features = []
    for number, (geometry, status, end) in enumerate(
        [
            (polygon + line, "bestaand", ""),
            (
                polygon,
                "bestaand",
                "<b:eindRegistratie>2020-01-01T00:00:00</b:eindRegistratie>",
            ),
            (polygon, "plan", ""),
            (point, "bestaand", ""),
            (polygon, "bestaand", "<b:objectEindTijd>2020-01-01</b:objectEindTijd>"),
        ]
    ):
        features.append(
            f'<gml:featureMember><b:Wegdeel gml:id="id.{number}"><b:bgt-status>{status}</b:bgt-status>{end}{geometry}<b:naam>behouden</b:naam></b:Wegdeel></gml:featureMember>'
        )
    xml = (
        '<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml" xmlns:b="https://example.com">'
        + "".join(features)
        + "</gml:FeatureCollection>"
    )
    archive = tmp_path / "bgt.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("bgt_wegdeel.gml", xml)
    output = tmp_path / "actueel"
    result = prepare_surface_layer(archive, output, "wegdeel")
    assert result is not None
    assert validate_surface_file(result, "bgt_wegdeel") == 1
    data = pyogrio.read_dataframe(result)
    assert data.gml_id.tolist() == ["id.0"]
    assert data.geom_type.tolist() == ["MultiPolygon"]
    assert data.area.tolist() == pytest.approx([100])
    assert data.naam.tolist() == ["behouden"]
    before = result.stat().st_mtime_ns
    assert prepare_surface_layer(archive, output, "wegdeel") == result
    assert result.stat().st_mtime_ns == before


def test_points_only_do_not_create_surface_file(tmp_path):
    xml = '<gml:FeatureCollection xmlns:gml="http://www.opengis.net/gml" xmlns:b="https://example.com"><gml:featureMember><b:VegetatieObject gml:id="1"><b:bgt-status>bestaand</b:bgt-status><b:geometrie2d><gml:Point><gml:pos>5 5</gml:pos></gml:Point></b:geometrie2d></b:VegetatieObject></gml:featureMember></gml:FeatureCollection>'
    archive = tmp_path / "bgt.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("bgt_vegetatieobject.gml", xml)
    output = tmp_path / "actueel"
    assert prepare_surface_layer(archive, output, "vegetatieobject") is None
    assert list(output.glob("*.gpkg")) == []
