import runpy
from pathlib import Path

import geopandas as gpd
import pyogrio
import pytest
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import Point, box

from waterlagen import _geopandas as wgpd
from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import select_bag_panden


@pytest.mark.parametrize("allowed", [True, False])
def test_combined_control_preserves_sources_and_explains_exclusion(tmp_path, allowed):
    store = DataStore(data_dir=tmp_path)
    path = store.bag_dir / "bag-light.gpkg"
    panden = gpd.GeoDataFrame(
        {
            "identificatie": ["p1", "p2", "p3"],
            "status": [
                "Pand in gebruik" if allowed else "Pand gesloopt",
                "Pand in gebruik (niet ingemeten)",
                None,
            ],
        },
        geometry=[box(i * 2, 0, i * 2 + 1, 1) for i in range(3)],
        crs="EPSG:28992",
    )
    vbo = gpd.GeoDataFrame(
        {
            "identificatie": ["v1"],
            "pand_identificatie": ["p1"],
            "gebruiksdoel": ["onderwijsfunctie,sportfunctie"],
            "oppervlakte": [9345],
        },
        geometry=[Point(0.5, 0.5)],
        crs=panden.crs,
    )
    panden.to_file(path, layer="pand", driver="GPKG")
    vbo.to_file(path, layer="verblijfsobject", driver="GPKG")
    script = Path(__file__).parents[1] / "scripts" / "controle_bag_landgebruik.py"
    main = runpy.run_path(str(script))["main"]
    target = main(store, bounds=(-1, -1, 6, 2), stap=5)
    assert pyogrio.list_layers(target)[:, 0].tolist() == ["bag_controle"]
    result = wgpd.read_file(target, layer="bag_controle")
    assert len(result) == 3
    assert result["meegenomen_stap2"].tolist() == [allowed, False, False]
    assert "ontbreekt" in result.iloc[2]["reden_statusselectie"]
    assert result["lgb_code_binnendijks"].isna().all()
    assert result["lgb_code_buitendijks"].isna().all()
    assert result.iloc[1]["klasse_status"] == "niet uitgevoerd: uitgesloten in stap 2"
    assert result.iloc[1]["bron_aantal_vbo"] == 0
    assert "Uitgesloten:" in result.iloc[1]["toelichting_resultaat"]
    if allowed:
        assert result.iloc[0]["berekend_aantal_bouwlagen"] == 9345
        assert result.iloc[0]["klasse_status"] == "nog te beoordelen"
        assert (
            "onderwijsfunctie, sportfunctie: 9.345 m² niet uitgesplitst"
            in result.iloc[0]["toelichting_resultaat"]
        )
        assert "onderwijsfunctie,sportfunctie" in result.iloc[0]["bron_vbo_overzicht"]
    original = wgpd.read_file(path, layer="pand")
    assert_geodataframe_equal(result[list(original.columns)], original)
    output_bytes = target.read_bytes()
    assert main(store, bounds=(-1, -1, 6, 2)) == target
    assert target.read_bytes() == output_bytes
    with pytest.raises(ValueError, match="status"):
        select_bag_panden(panden.drop(columns="status"))

    # Default execution combines both examples in one layer.
    main.__globals__["BOUNDS"] = (-1, -1, 2, 2)
    main.__globals__["WINKEL_WONING_BOUNDS"] = (3, -1, 6, 2)
    combined = main(store, stap=5)
    combined_data = wgpd.read_file(combined, layer="bag_controle")
    assert set(combined_data["uitsnede"]) == {"Flik-Flak", "Vughterstraat"}
    assert pyogrio.list_layers(combined)[:, 0].tolist() == ["bag_controle"]
