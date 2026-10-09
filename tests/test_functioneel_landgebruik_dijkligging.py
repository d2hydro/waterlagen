import geopandas as gpd
import pytest
from shapely.geometry import GeometryCollection, box

from waterlagen.functioneel_landgebruik.bronnen_voorbereiden import prepare_water
from waterlagen.functioneel_landgebruik.landgebruik_berekenen import (
    FunctioneelLandgebruikLayers,
    FunctioneelLandgebruikSources,
    _download_missing_sources,
    _read_buitendijks_area,
)


@pytest.mark.parametrize(
    "geometry,code",
    [
        (box(2, 2, 4, 4), 228),  # Clearly inside LIWO.
        (box(12, 2, 14, 4), 100),  # Outside LIWO.
        (box(-1, 2, 1, 4), 228),  # Representative point on boundary.
        (box(-2, 2, 0, 4), 100),  # Object only touches boundary.
        (box(-2, 2, 1, 4), 100),  # Overlap, representative point outside.
        (box(-0.999, 2, 1, 4), 228),  # Just inside.
        (box(-1.001, 2, 1, 4), 100),  # Just outside.
    ],
)
def test_liwo_selects_landuse_code_with_representative_point(tmp_path, geometry, code):
    path = tmp_path / "bgt.gpkg"
    data = gpd.GeoDataFrame(
        {
            "bgt-status": ["bestaand"],
            "eindRegistratie": [None],
            "objectEindTijd": [None],
        },
        geometry=[geometry],
        crs=28992,
    )
    data.to_file(path, layer="bgt_waterdeel", driver="GPKG")
    result = prepare_water(
        path,
        layer="bgt_waterdeel",
        bounds=(-5, -5, 20, 20),
        buitendijks_area=box(0, 0, 10, 10),
    )
    assert result["code"].tolist() == [code]
    assert result.geometry.iloc[0].equals(geometry)


def test_empty_liwo_is_valid_and_covers_no_objects(tmp_path):
    path = tmp_path / "liwo.gpkg"
    gpd.GeoDataFrame(geometry=[], crs=28992).to_file(
        path,
        layer="buitendijks_gebied_uit_liwo",
        driver="GPKG",
    )
    area = _read_buitendijks_area(
        FunctioneelLandgebruikSources(buitendijks_gpkg=path),
        FunctioneelLandgebruikLayers(),
    )
    assert isinstance(area, GeometryCollection)
    assert area.is_empty


def test_missing_liwo_fails_before_downloading_other_sources(tmp_path):
    sources = FunctioneelLandgebruikSources(buitendijks_gpkg=tmp_path / "missing.gpkg")
    with pytest.raises(
        FileNotFoundError, match="liwo_overstromingsgevoelige_gebieden.py"
    ):
        _download_missing_sources(sources, FunctioneelLandgebruikLayers())
