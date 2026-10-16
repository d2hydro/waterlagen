"""Tools for preparing vector input for afwateringseenheden."""

from .brandlagen import read_brandlagen
from .config import Brandlaag, BrandlagenConfig, read_brandlagen_config
from .lines import (
    WatersysteemResult,
    split_hydroobjecten_at_points,
    split_hydroobjecten_by_length,
)
from .objects import (
    read_hydroobjecten,
    read_puntobjecten,
    waterbeheercode_from_nen3610id,
)
from .pcraster import SubcatchmentResult, calculate_subcatchments, require_pcraster
from .raster import WatersysteemRasters, prepare_watersysteem_rasters
from .sources import WatersysteemSources, read_watersysteem_sources
from .tiles import (
    AfwateringseenhedenTileResult,
    AfwateringseenhedenTilesResult,
    calculate_afwateringseenheden_tiles,
)
from .workflow import (
    prepare_watersysteem,
    split_connected_secondary_hydroobjecten,
    write_watersysteem,
)

__all__ = [
    "AfwateringseenhedenTileResult",
    "AfwateringseenhedenTilesResult",
    "Brandlaag",
    "BrandlagenConfig",
    "SubcatchmentResult",
    "WatersysteemRasters",
    "WatersysteemResult",
    "WatersysteemSources",
    "calculate_afwateringseenheden_tiles",
    "calculate_subcatchments",
    "prepare_watersysteem",
    "prepare_watersysteem_rasters",
    "read_brandlagen",
    "read_brandlagen_config",
    "read_hydroobjecten",
    "read_puntobjecten",
    "read_watersysteem_sources",
    "require_pcraster",
    "split_connected_secondary_hydroobjecten",
    "split_hydroobjecten_at_points",
    "split_hydroobjecten_by_length",
    "waterbeheercode_from_nen3610id",
    "write_watersysteem",
]
