import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import prepare_bag


@pytest.mark.parametrize("with_vbo", [False, True])
def test_bag_keeps_only_notitie_statuses(tmp_path, with_vbo):
    statuses = [
        "Bouw gestart",
        "Pand in gebruik",
        "Verbouwing pand",
        "Pand in gebruik (niet ingemeten)",
        "Pand buiten gebruik",
        "Bouwvergunning verleend",
        "Sloopvergunning verleend",
        "Pand gesloopt",
        "Pand ten onrechte opgevoerd",
        None,
        "",
        "onbekend",
    ]
    ids = [f"p{i}" for i in range(len(statuses))]
    panden = gpd.GeoDataFrame(
        {"identificatie": ids, "status": statuses},
        geometry=[box(i * 2, 0, i * 2 + 1, 1) for i in range(len(ids))],
        crs="EPSG:28992",
    )
    vbo = gpd.GeoDataFrame(
        {
            "identificatie": [f"v{i}" for i in range(len(ids))],
            "pand_identificatie": ids,
            "gebruiksdoel": ["kantoorfunctie"] * len(ids),
            "oppervlakte": [50] * len(ids),
        },
        geometry=[Point(i * 2 + 0.5, 0.5) for i in range(len(ids))],
        crs=panden.crs,
    )
    if not with_vbo:
        vbo = vbo.iloc[:0]
    path = tmp_path / "bag.gpkg"
    panden.to_file(path, layer="pand", driver="GPKG")
    vbo.to_file(path, layer="verblijfsobject", driver="GPKG")
    kwargs = {
        "pand_layer": "pand",
        "verblijfsobject_layer": "verblijfsobject",
        "bounds": (-1, -1, 30, 2),
        "dike_area": box(-1, -1, 30, 2),
        "include_details": True,
    }
    result = prepare_bag(path, **kwargs)
    assert result["identificatie"].tolist() == ids[:3]
    assert result["status"].tolist() == statuses[:3]
    assert result["code"].tolist() == ([19] * 3 if with_vbo else [34] * 3)

    # An area with only excluded statuses should produce an empty result.
    kwargs["bounds"] = (6, -1, 30, 2)
    assert prepare_bag(path, **kwargs).empty
