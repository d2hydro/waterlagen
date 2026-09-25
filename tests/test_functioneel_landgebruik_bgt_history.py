import geopandas as gpd
import pytest
from shapely.geometry import box

from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import (
    prepare_water,
    prepare_wegen,
)


@pytest.mark.parametrize("roads", [False, True])
@pytest.mark.parametrize("missing_field", [None, "eindRegistratie", "objectEindTijd"])
def test_bgt_current_registration_only(tmp_path, roads, missing_field):
    path = tmp_path / "bgt.gpkg"
    layer = "bgt_wegdeel" if roads else "bgt_waterdeel"
    data = gpd.GeoDataFrame(
        {
            "lokaalID": ["same", "same", "ended", "both", "planned", "unknown"],
            "bgt-status": ["bestaand"] * 4 + ["plan", None],
            "bgt-functie": ["voetpad"] * 6,
            "eindRegistratie": [None, "2026-01-01", None, "2026-01-01", None, None],
            "objectEindTijd": [None, None, "2026-01-01", "2026-01-01", None, None],
        },
        geometry=[box(i * 2, 0, i * 2 + 1, 1) for i in range(6)],
        crs="EPSG:28992",
    )
    if missing_field:
        data = data.drop(columns=missing_field)
    data.to_file(path, layer=layer, driver="GPKG")
    prepare = prepare_wegen if roads else prepare_water
    kwargs = {"layer": layer, "bounds": (-1, -1, 20, 2)}
    if roads:
        kwargs["dike_area"] = box(-1, -1, 20, 2)
    if missing_field:
        with pytest.raises(ValueError, match=missing_field):
            prepare(path, **kwargs)
        return
    result = prepare(path, **kwargs)
    assert len(result) == 1
    assert result.geometry.iloc[0].equals(data.geometry.iloc[0])
    assert result["code"].iloc[0] == (75 if roads else 100)
    # A window containing only the ended registrations must remain empty.
    kwargs["bounds"] = (2, -1, 20, 2)
    assert prepare(path, **kwargs).empty
