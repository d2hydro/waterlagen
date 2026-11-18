"""Lees kaartgebieden uit dezelfde bronnen als de productie."""

import geopandas as gpd
from shapely.geometry import Polygon, mapping
from shapely.ops import orient

from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._sources import SourcePreparation
from waterlagen.administratieve_gebieden import (
    download_waterschapsgrenzen,
    normaliseer_waterschapsgrenzen,
    read_waterschapsgrenzen_layer,
)
from waterlagen.administratieve_gebieden.download import WATERSCHAPSGRENZEN_FILENAME
from waterlagen.areas import ProductionArea, area_from_file, resolve_area
from waterlagen.datastore import DataStore
from waterlagen.settings import settings
from pathlib import Path


def map_feature(area: ProductionArea) -> dict:
    """Toon een productiegebied in WGS84; de brongeometrie blijft ongewijzigd."""
    frame = gpd.GeoDataFrame(geometry=[area.geometry], crs=area.crs).to_crs(4326)
    return {
        "type": "Feature",
        "properties": {},
        "geometry": mapping(orient(frame.geometry.iloc[0], sign=-1)),
    }


def map_boundaries(names: dict[str, str]) -> dict:
    """Hergebruik lokale grenzen; haal alleen ontbrekende grensbestanden op."""
    store = DataStore()
    preparation = SourcePreparation()
    source = store.administratieve_gebieden_dir / WATERSCHAPSGRENZEN_FILENAME
    preparation.ensure(
        source,
        lambda: download_waterschapsgrenzen(download_dir=source.parent, progress=False),
    )
    frame = normaliseer_waterschapsgrenzen(
        read_waterschapsgrenzen_layer(path=source)
    ).to_crs(settings.crs)
    # Eén meter vereenvoudiging is alleen voor weergave, nooit voor productie.
    frame.geometry = frame.geometry.simplify(1, preserve_topology=True)
    frame = frame.to_crs(4326)
    features = []
    for row in frame.itertuples():
        code = str(row.waterbeheercode)
        if code in names:
            features.append(
                {
                    "type": "Feature",
                    "properties": {"code": code, "name": names[code]},
                    "geometry": mapping(orient(row.geometry, sign=-1)),
                }
            )
    country = resolve_area("nederland", store, preparation)
    return {
        "authorities": {"type": "FeatureCollection", "features": features},
        "country": map_feature(country),
    }


def save_polygon(coordinates: list, path: Path) -> dict:
    """Bewaar een getekend WGS84-vlak in het project-CRS, naast bestaande lagen."""
    if path.suffix.lower() != ".gpkg":
        raise ValueError("Bewaar het gebied als .gpkg.")
    if not 3 <= len(coordinates) <= 100_000:
        raise ValueError("Teken minstens drie hoekpunten.")
    for point in coordinates:
        if len(point) != 2 or not (-180 <= point[0] <= 180 and -85 <= point[1] <= 85):
            raise ValueError("Ongeldige kaartcoördinaten.")
    polygon = Polygon(coordinates)
    if polygon.is_empty or not polygon.is_valid or polygon.area == 0:
        raise ValueError(
            "De polygoon kruist zichzelf of heeft geen oppervlakte. Pas de punten aan."
        )
    frame = gpd.GeoDataFrame({"naam": ["gebied"]}, geometry=[polygon], crs=4326).to_crs(
        settings.crs
    )
    write_geopackage_layer_atomically(
        frame, path, layer_name="gebied", preserve_other_layers=True
    )
    return map_feature(area_from_file(path, layer="gebied"))
