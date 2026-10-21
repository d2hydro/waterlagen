"""Prepare joint raster connectivity without changing the RWS target policy."""

import json
from dataclasses import dataclass
from math import ceil, floor
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window, from_bounds
from scipy.ndimage import binary_dilation, label
from shapely.geometry import Point, box
from shapely.geometry.base import BaseGeometry

from waterlagen._geopackage import write_geopackage_layer_atomically
from waterlagen._production import _file_identity
from waterlagen.logger import get_logger
from waterlagen.raster.grid import RasterGrid

from .brandlagen import _digest, _rasterize_brand_shapes, _sort_brandlagen
from .config import BrandlagenConfig
from .duikers import _frame_identity
from .sources import WatersysteemSources

logger = get_logger(__name__)
WATERNET_POLICY = "prepared_primary_pieces_separate_culvert_rasters_v3"
NEIGHBOURS = np.ones((3, 3), dtype=bool)


@dataclass
class _ComponentTile:
    grid: RasterGrid
    path: Path
    offset: int
    count: int


@dataclass(frozen=True)
class _CulvertContacts:
    count: int
    has_lower: bool


class _Components:
    def __init__(self) -> None:
        self.parents = [0]

    def add(self, count: int) -> int:
        offset = len(self.parents) - 1
        self.parents.extend(range(offset + 1, offset + count + 1))
        return offset

    def root(self, item: int) -> int:
        while self.parents[item] != item:
            self.parents[item] = self.parents[self.parents[item]]
            item = self.parents[item]
        return item

    def join(self, first: int, second: int) -> None:
        a, b = self.root(first), self.root(second)
        if a != b:
            self.parents[max(a, b)] = min(a, b)


def _local_grid(geometry, grid: RasterGrid) -> RasterGrid:
    x0, y0, x1, y1 = geometry.bounds
    size = grid.resolution
    ox, oy = grid.transform.c, grid.transform.f
    bounds = (
        ox + (floor((x0 - ox) / size) - 2) * size,
        oy + (floor((y0 - oy) / size) - 2) * size,
        ox + (ceil((x1 - ox) / size) + 2) * size,
        oy + (ceil((y1 - oy) / size) + 2) * size,
    )
    return RasterGrid.from_bounds(bounds, resolution=size, crs=grid.crs)


def _mask(geometries, grid: RasterGrid) -> np.ndarray:
    return _rasterize_brand_shapes(
        [(g, 1) for g in geometries if g is not None and not g.is_empty],
        out_shape=(grid.height, grid.width),
        transform=grid.transform,
        dtype="uint8",
    ).astype(bool)


def _nearby(frame: gpd.GeoDataFrame, grid: RasterGrid) -> gpd.GeoDataFrame:
    indices = frame.sindex.query(box(*grid.bounds), predicate="intersects")
    return frame.iloc[sorted(indices)]


def _endpoints(geometry) -> list[Point]:
    if geometry.geom_type == "LineString":
        return [Point(geometry.coords[0]), Point(geometry.coords[-1])]
    if geometry.geom_type == "MultiLineString":
        return [point for part in geometry.geoms for point in _endpoints(part)]
    return []


def _raster_equivalent(first, second, grid: RasterGrid) -> bool:
    """Require coverage in both directions; crossing culverts are not duplicates."""
    local = _local_grid(first.union(second), grid)
    a, b = _mask([first], local), _mask([second], local)
    return bool(
        a.any()
        and b.any()
        and np.all(binary_dilation(b, structure=NEIGHBOURS)[a])
        and np.all(binary_dilation(a, structure=NEIGHBOURS)[b])
    )


def _culvert_contacts(
    geometry: BaseGeometry,
    grid: RasterGrid,
    primary: np.ndarray,
    lower: gpd.GeoDataFrame,
) -> _CulvertContacts:
    """Count endpoint/side contacts, retaining the polygon contact-zone rule."""
    footprint = _mask([geometry], grid)
    vicinity = binary_dilation(footprint, structure=NEIGHBOURS)
    lower_mask = _mask(lower.geometry, grid)
    contacts = (primary | lower_mask) & vicinity & ~footprint
    _, zone_count = label(contacts, structure=NEIGHBOURS)
    side_points = [point for line in lower.geometry for point in _endpoints(line)]
    side = _mask(side_points, grid) & footprint
    endpoints = _endpoints(geometry)
    if not endpoints:
        # A lower endpoint at an outside contact zone is the same attachment.
        side &= ~binary_dilation(contacts, structure=NEIGHBOURS)
        _, side_count = label(side, structure=NEIGHBOURS)
        return _CulvertContacts(
            zone_count + side_count, bool((lower_mask & vicinity).any())
        )
    # Do not count a waterline endpoint at a culvert end a second time as a side
    # connection. Interior attachments (such as the FID 85 case) still count.
    side &= ~binary_dilation(_mask(endpoints, grid), structure=NEIGHBOURS)
    _, side_count = label(side, structure=NEIGHBOURS)
    water_vicinity = binary_dilation(primary | lower_mask, structure=NEIGHBOURS)
    lower_vicinity = binary_dilation(lower_mask, structure=NEIGHBOURS)
    end_count = 0
    attached_lower = bool(side_count)
    for point in endpoints:
        point_mask = _mask([point], grid)
        end_count += bool((point_mask & water_vicinity).any())
        attached_lower |= bool((point_mask & lower_vicinity).any())
    return _CulvertContacts(end_count + side_count, attached_lower)


def _classify_culverts(
    sources: WatersysteemSources,
    optional: gpd.GeoDataFrame,
    grid: RasterGrid,
) -> gpd.GeoDataFrame:
    records = []
    next_code = int(optional.broncode.max()) + 1 if not optional.empty else 3
    if sources.culverts is not None:
        for row in sources.culverts.itertuples():
            records.append(
                {
                    "geometry": row.geometry,
                    "bron": "hydamo",
                    "rang": 0,
                    "broncode": next_code,
                    "bronbestand": row.bronbestand,
                    "bronlaag": row.bronlaag,
                    "bron_fid": int(row.bron_fid),
                    "bron_id": row.bron_id,
                }
            )
    if "rol" in optional:
        for row in optional.loc[optional.rol.eq("duiker")].itertuples():
            records.append(
                {
                    "geometry": row.geometry,
                    "bron": row.bron,
                    "rang": {"hydamo": 0, "bgt": 1, "osm": 2}[row.bron],
                    "broncode": int(row.broncode),
                    "bronbestand": row.bronbestand,
                    "bronlaag": row.bronlaag,
                    "bron_fid": int(row.bron_fid),
                    "bron_id": f"{row.bronbestand}|{row.bronlaag}|{row.bron_fid}",
                }
            )
    columns = [
        "geometry",
        "bron",
        "rang",
        "broncode",
        "bronbestand",
        "bronlaag",
        "bron_fid",
        "bron_id",
        "behandeling",
        "diep_geschikt",
        "reden",
        "voorkeur_id",
    ]
    if not records:
        return gpd.GeoDataFrame(columns=columns, geometry="geometry", crs=grid.crs)
    culverts = (
        gpd.GeoDataFrame(records, crs=grid.crs)
        .sort_values(["rang", "bronbestand", "bronlaag", "bron_fid"], kind="stable")
        .reset_index(drop=True)
    )
    culverts["behandeling"] = "controle"
    culverts["diep_geschikt"] = False
    culverts["reden"] = ""
    culverts["voorkeur_id"] = ""
    lower = sources.secondary
    if sources.tertiary is not None:
        lower = gpd.GeoDataFrame(pd.concat([lower, sources.tertiary]), crs=grid.crs)
    accepted = set()
    for index, row in culverts.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty or not geometry.is_valid:
            culverts.loc[index, "reden"] = "ongeldige geometrie"
            continue
        candidates = culverts.sindex.query(
            box(*geometry.bounds).buffer(grid.resolution * 2), predicate="intersects"
        )
        matches = [
            i
            for i in sorted(candidates)
            if i in accepted
            and culverts.loc[i, "rang"] < row.rang
            and _raster_equivalent(geometry, culverts.geometry.iloc[i], grid)
        ]
        if matches:
            if len(matches) == 1:
                culverts.loc[index, ["behandeling", "voorkeur_id"]] = [
                    "dubbel",
                    culverts.loc[matches[0], "bron_id"],
                ]
            else:
                culverts.loc[index, "reden"] = "meerdere mogelijke bronduplicaten"
            continue
        local = _local_grid(geometry, grid)
        primary = _mask(_nearby(sources.primary, local).geometry, local)
        lower_frame = _nearby(lower, local)
        contacts = _culvert_contacts(geometry, local, primary, lower_frame)
        if contacts.count < 2:
            culverts.loc[index, "reden"] = "minder dan twee rasteraansluitingen"
        elif contacts.has_lower:
            culverts.loc[index, "behandeling"] = "aanvoer"
            if row.bron == "hydamo":
                secondary_contacts = _culvert_contacts(
                    geometry, local, primary, _nearby(sources.secondary, local)
                )
                culverts.loc[index, "diep_geschikt"] = (
                    secondary_contacts.count >= 2 and secondary_contacts.has_lower
                )
        elif primary.any():
            culverts.loc[index, "behandeling"] = "primair_primair"
        else:
            culverts.loc[index, "reden"] = "geen waterloopaansluiting"
        accepted.add(index)
        if (index + 1) % 2000 == 0:
            logger.info(
                "Classified %s/%s culvert registrations", index + 1, len(culverts)
            )
    return culverts


def waternet_path(watersysteem: Path, grid: RasterGrid) -> Path:
    key = _digest((tuple(float(v) for v in grid.bounds), float(grid.resolution)))[:20]
    return watersysteem.parent / "waternet" / f"{key}.tif"


def _write_grid(
    path: Path,
    grid: RasterGrid,
    arrays: list[np.ndarray],
    tags: dict,
    *,
    dtype: str = "int32",
) -> None:
    temporary = path.with_suffix(".tmp.tif")
    try:
        with rasterio.open(
            temporary,
            "w",
            driver="GTiff",
            width=grid.width,
            height=grid.height,
            count=len(arrays),
            dtype=dtype,
            crs=grid.crs,
            transform=grid.transform,
            tiled=True,
            compress="deflate",
            BIGTIFF="IF_SAFER",
        ) as target:
            for band, array in enumerate(arrays, 1):
                target.write(array.astype(dtype, copy=False), band)
            target.update_tags(**tags)
        with rasterio.open(temporary) as source:
            if source.shape != (grid.height, grid.width) or source.count != len(arrays):
                raise ValueError("Invalid waternet raster")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _join_tiles(a: _ComponentTile, b: _ComponentTile, components: _Components) -> None:
    overlap = box(*a.grid.bounds).intersection(box(*b.grid.bounds))
    if overlap.is_empty or overlap.area == 0:
        return
    with rasterio.open(a.path) as first, rasterio.open(b.path) as second:
        wa = (
            from_bounds(*overlap.bounds, first.transform)
            .round_offsets()
            .round_lengths()
        )
        wb = (
            from_bounds(*overlap.bounds, second.transform)
            .round_offsets()
            .round_lengths()
        )
        for start in range(0, int(wa.height), 256):
            height = min(256, int(wa.height) - start)
            av = first.read(
                1, window=Window(wa.col_off, wa.row_off + start, wa.width, height)
            )
            bv = second.read(
                1, window=Window(wb.col_off, wb.row_off + start, wb.width, height)
            )
            valid = (av > 0) & (bv > 0)
            pairs = np.unique(np.column_stack((av[valid], bv[valid])), axis=0)
            for x, y in pairs:
                components.join(int(x) + a.offset, int(y) + b.offset)


def _culvert_burn_geometries(
    culverts: gpd.GeoDataFrame, primary_pieces: gpd.GeoDataFrame | None
) -> gpd.GeoDataFrame:
    """Keep matched pieces separate so rasterization preserves vertex order."""
    result = culverts.copy()
    if primary_pieces is None or primary_pieces.empty:
        return result
    pieces_by_culvert: dict[str, list[BaseGeometry]] = {}
    for row in primary_pieces.itertuples():
        for identifier in json.loads(row.duiker_ids):
            pieces_by_culvert.setdefault(identifier, []).append(row.geometry)
    additional = []
    for _, row in result.iterrows():
        pieces = pieces_by_culvert.get(row.bron_id, [])
        if pieces and row.behandeling in ("aanvoer", "primair_primair"):
            for geometry in pieces:
                part = row.copy()
                part["geometry"] = geometry
                additional.append(part)
    if additional:
        result = gpd.GeoDataFrame(
            pd.concat(
                [result, gpd.GeoDataFrame(additional, crs=result.crs)],
                ignore_index=True,
            ),
            geometry="geometry",
            crs=result.crs,
        )
    return result


def _shallow_depths(
    optional: gpd.GeoDataFrame,
    grid: RasterGrid,
    treatment: np.ndarray,
    source_codes: np.ndarray,
    default_depth: float,
) -> np.ndarray:
    """Keep configured additional-source depths only in their own shallow cells."""
    depths = np.full(source_codes.shape, default_depth, dtype="float32")
    if "brandwaarde" not in optional or "rol" not in optional:
        return depths
    features = _nearby(optional, grid)
    features = features.loc[features.rol.isin(["water", "duiker"])]
    for code, group in features.groupby("broncode", sort=False):
        selected = (treatment == 3) & (source_codes == code)
        if not selected.any():
            continue
        ordered = _sort_brandlagen(group)
        values = _rasterize_brand_shapes(
            list(zip(ordered.geometry, ordered.brandwaarde)),
            out_shape=source_codes.shape,
            transform=grid.transform,
            dtype="float32",
        )
        depths[selected] = -values[selected]
    return depths


def prepare_waternet(
    sources: WatersysteemSources,
    optional: gpd.GeoDataFrame,
    grids: list[RasterGrid],
    watersysteem: Path,
    config: BrandlagenConfig,
    *,
    primary_culvert_pieces: gpd.GeoDataFrame | None = None,
) -> None:
    """Prepare globally connected components once, independently of worker count.

    Only primary, secondary and eligible HYDAMO culverts establish deep-network
    connectivity. Additional water cannot promote isolated lines to deep burns.
    Components from overlapping buffered tiles are joined before depths are
    assigned. Primary RWS remains a deep burn seed, without becoming a target.
    Culvert diagnostics preserve all registrations, including duplicates.
    """
    directory = watersysteem.parent / "waternet"
    directory.mkdir(exist_ok=True)
    manifest = directory / "manifest.json"
    signature = _digest(
        {
            "policy": WATERNET_POLICY,
            "primary": _frame_identity(sources.primary),
            "secondary": _frame_identity(sources.secondary),
            "tertiary": _frame_identity(sources.tertiary)
            if sources.tertiary is not None
            else None,
            "culverts": _frame_identity(sources.culverts)
            if sources.culverts is not None
            else None,
            "optional": _frame_identity(optional),
            "primary_culvert_pieces": _frame_identity(primary_culvert_pieces)
            if primary_culvert_pieces is not None
            else None,
            "grids": [(g.bounds, g.resolution, str(g.crs)) for g in grids],
            "shallow": config.geisoleerde_branddiepte_m,
            "watersysteem": _file_identity(watersysteem),
        }
    )
    if manifest.exists():
        previous = json.loads(manifest.read_text(encoding="utf-8"))
        if previous.get("signature") == signature and all(
            identity == _file_identity(directory / name)
            for name, identity in previous["rasters"].items()
        ):
            logger.info("Reusing joint waternet preparation %s", directory)
            return
    manifest.unlink(missing_ok=True)
    logger.info("Preparing joint water/culvert connectivity on %s grids", len(grids))
    culverts = _classify_culverts(sources, optional, grids[0])
    write_geopackage_layer_atomically(
        culverts,
        watersysteem.parent / "controle.gpkg",
        layer_name="duikers_waternet",
        preserve_other_layers=True,
    )
    logger.info("Culvert treatments: %s", culverts.behandeling.value_counts().to_dict())
    effective = _culvert_burn_geometries(
        culverts.loc[~culverts.behandeling.eq("dubbel")], primary_culvert_pieces
    )
    primary_burn = sources.primary
    if primary_culvert_pieces is not None:
        primary_burn = primary_culvert_pieces.loc[
            primary_culvert_pieces.brandgeschikt.astype(bool)
        ]
    components = _Components()
    seeds = set()
    tiles = []
    legend = {1: "HYDAMO/RWS primair", 2: "HYDAMO secundair"}
    for row in optional.itertuples():
        legend[int(row.broncode)] = f"{row.bronbestand} / {row.bronlaag}"
    hydro_culvert_code = int(optional.broncode.max()) + 1 if not optional.empty else 3
    tertiary_code = hydro_culvert_code + 1
    legend[hydro_culvert_code] = "HYDAMO duikersifonhevel"
    legend[tertiary_code] = "HYDAMO tertiair"
    for number, grid in enumerate(grids, 1):
        path = waternet_path(watersysteem, grid)
        logger.info(
            "Raster connectivity grid %s/%s: %s", number, len(grids), grid.bounds
        )
        water = _nearby(optional, grid)
        if "rol" in water:
            water = water.loc[water.rol.eq("water")]
        else:
            water = water.iloc[:0]
        source_codes = _rasterize_brand_shapes(
            list(zip(water.geometry, water.broncode)),
            out_shape=(grid.height, grid.width),
            transform=grid.transform,
            dtype="int32",
        )
        if sources.tertiary is not None:
            source_codes[_mask(_nearby(sources.tertiary, grid).geometry, grid)] = (
                tertiary_code
            )
        local = _nearby(effective, grid)
        supply = local.loc[local.behandeling.eq("aanvoer")].sort_values(
            "rang", ascending=False
        )
        shallow_supply = supply.loc[~supply.diep_geschikt.astype(bool)]
        for rank in sorted(shallow_supply.rang.unique(), reverse=True):
            group = shallow_supply.loc[shallow_supply.rang.eq(rank)]
            codes = _rasterize_brand_shapes(
                list(zip(group.geometry, group.broncode)),
                out_shape=source_codes.shape,
                transform=grid.transform,
                dtype="int32",
            )
            active = codes != 0
            source_codes[active] = codes[active]
        # HYDAMO waterlines and eligible culverts take precedence over shallow
        # sources, including non-duplicate BGT/OSM culverts that cross them.
        secondary = _mask(_nearby(sources.secondary, grid).geometry, grid)
        source_codes[secondary] = 2
        primary = _mask(_nearby(primary_burn, grid).geometry, grid)
        source_codes[primary] = 1
        deep_supply = supply.loc[supply.diep_geschikt.astype(bool)]
        culvert_codes = _rasterize_brand_shapes(
            list(zip(deep_supply.geometry, deep_supply.broncode)),
            out_shape=source_codes.shape,
            transform=grid.transform,
            dtype="int32",
        )
        deep_culverts = culvert_codes != 0
        if primary_culvert_pieces is not None:
            # A crossing allowed primary piece keeps its own burn and target.
            deep_culverts &= ~primary
        source_codes[deep_culverts] = culvert_codes[deep_culverts]
        primary[deep_culverts] = False
        deep_network = secondary | deep_culverts
        excluded = _mask(
            local.loc[local.behandeling.eq("primair_primair")].geometry, grid
        )
        # Only an eligible HYDAMO connection can override primary-only exclusion.
        excluded &= ~deep_culverts
        if primary_culvert_pieces is not None:
            excluded &= ~(primary | secondary)
        source_codes[excluded] = 0
        primary[excluded] = False
        deep_network[excluded] = False
        no_target = _mask(
            local.loc[local.behandeling.isin(["primair_primair", "aanvoer"])].geometry,
            grid,
        )
        if primary_culvert_pieces is not None:
            no_target &= ~primary
        labels, count = label(primary | deep_network, structure=NEIGHBOURS)
        offset = components.add(count)
        seeds.update(int(v) + offset for v in np.unique(labels[primary]) if v)
        # 1 = primary, 2 = potentially deep HYDAMO, 3 = shallow, 4 = excluded.
        treatment = np.where(source_codes != 0, 3, 0).astype("int32")
        treatment[deep_network] = 2
        treatment[primary] = 1
        treatment[excluded] = 4
        _write_grid(path, grid, [labels, treatment, source_codes, no_target], {})
        tile = _ComponentTile(grid, path, offset, count)
        for previous in tiles:
            _join_tiles(tile, previous, components)
        tiles.append(tile)
        del labels, treatment, source_codes, primary, excluded, no_target
        del secondary, deep_network, deep_culverts, culvert_codes
    connected = {components.root(value) for value in seeds}
    for tile in tiles:
        with rasterio.open(tile.path) as source:
            arrays = [source.read(band) for band in (1, 2, 3, 4)]
        lookup = np.zeros(tile.count + 1, dtype=bool)
        for value in range(1, tile.count + 1):
            lookup[value] = components.root(value + tile.offset) in connected
        labels, treatment, codes, no_target = arrays
        treatment[(treatment == 2) & ~lookup[labels]] = 3
        shallow_depths = _shallow_depths(
            optional, tile.grid, treatment, codes, config.geisoleerde_branddiepte_m
        )
        _write_grid(
            tile.path,
            tile.grid,
            [treatment, codes, no_target, shallow_depths],
            {
                "policy": WATERNET_POLICY,
                "broncodes": json.dumps(legend),
                "shallow_depth_m": str(config.geisoleerde_branddiepte_m),
            },
            dtype="float64",
        )
    data = {
        "signature": signature,
        "policy": WATERNET_POLICY,
        "watersysteem": _file_identity(watersysteem),
        "rasters": {tile.path.name: _file_identity(tile.path) for tile in tiles},
    }
    temporary = manifest.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.replace(manifest)


def read_waternet(
    watersysteem: Path,
    grid: RasterGrid,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[int, str], np.ndarray] | None:
    """Read the prepared treatment, provenance and target-exclusion masks."""
    manifest = watersysteem.parent / "waternet" / "manifest.json"
    if not manifest.exists():
        return None
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    path = waternet_path(watersysteem, grid)
    if (
        metadata["policy"] != WATERNET_POLICY
        or metadata["watersysteem"] != _file_identity(watersysteem)
        or metadata["rasters"].get(path.name) != _file_identity(path)
    ):
        raise ValueError("Waternet preparation is stale or missing for this grid")
    with rasterio.open(path) as source:
        if source.transform != grid.transform or source.shape != (
            grid.height,
            grid.width,
        ):
            raise ValueError("Waternet grid mismatch")
        return (
            source.read(1, out_dtype="int32"),
            source.read(2, out_dtype="int32"),
            source.read(3).astype(bool),
            {int(k): v for k, v in json.loads(source.tags()["broncodes"]).items()},
            source.read(4, out_dtype="float32"),
        )
