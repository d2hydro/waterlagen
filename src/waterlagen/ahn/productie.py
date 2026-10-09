"""Prepare a reusable AHN tile cache and a production-specific VRT."""

from pathlib import Path

from shapely.geometry.base import BaseGeometry

from waterlagen._crs import same_crs
from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._geopandas import read_file
from waterlagen._sources import SourcePreparation, prepare_cached
from waterlagen.ahn import AHNService, download_ahn, get_tiles_features
from waterlagen.ahn.download import _is_valid_ahn_tile
from waterlagen.datastore import DataStore
from waterlagen.raster.vrt import create_vrt_file
from waterlagen.settings import settings


def prepare_ahn(
    store: DataStore,
    geometry: BaseGeometry,
    target_vrt: Path,
    preparation: SourcePreparation,
) -> Path:
    """Prepare DTM tiles; offline requires a cached index and valid tiles.

    Parameters
    ----------
    store : DataStore
        AHN source cache location.
    geometry : shapely.geometry.base.BaseGeometry
        Required context in ``settings.crs``. Whole AHN tiles are retained.
    target_vrt : pathlib.Path
        Run-specific mosaic, reused while source identities match.
    preparation : SourcePreparation
        Shared reuse, refresh and offline policy.

    Returns
    -------
    pathlib.Path
        VRT referencing the required original DTM tiles.
    """
    index_path = store.ahn_dir / "ahn_dtm_05_index.gpkg"

    def download_index() -> None:
        index = get_tiles_features(ahn_service=AHNService(service="ahn_pdok"))
        index["tile_id"] = index.index.astype(str)
        write_geopackage_layer_atomically(
            index.reset_index(drop=True), index_path, layer_name="tiles"
        )

    preparation.ensure(index_path, download_index)
    index = read_file(index_path, layer="tiles").set_index("tile_id")
    if not same_crs(index.crs, settings.crs):
        index = index.to_crs(settings.crs)
    selected = index.loc[index.intersects(geometry)]
    if selected.empty:
        raise ValueError("Geen AHN-tegels in het benodigde rekengebied")
    directory = store.ahn_dir / "dtm_05"
    paths = [directory / f"{name}.tif" for name in selected.index]
    pending = []
    for name, path in zip(selected.index, paths, strict=True):
        valid = path.is_file() and _is_valid_ahn_tile(path)
        if not valid or (
            preparation.refresh and path.resolve() not in preparation.prepared
        ):
            if preparation.offline:
                raise FileNotFoundError(
                    f"Geldige AHN-tegel ontbreekt in offline modus: {path}"
                )
            pending.append(name)
    if pending:
        download_ahn(
            ahn_dir=store.ahn_dir,
            tile_index=selected.loc[pending],
            missing_only=not preparation.refresh,
            create_vrt=False,
        )
    preparation.prepared.update(path.resolve() for path in paths)
    return prepare_cached(
        target_vrt,
        {path.name: path for path in paths},
        lambda: create_vrt_file(target_vrt, files=paths),
    )
