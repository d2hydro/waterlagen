"""Tools for preparing vector input for afwateringseenheden."""

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
from .pcraster import require_pcraster
from .workflow import (
    prepare_watersysteem,
    split_connected_secondary_hydroobjecten,
    write_watersysteem,
)

__all__ = [
    "WatersysteemResult",
    "prepare_watersysteem",
    "read_hydroobjecten",
    "read_puntobjecten",
    "require_pcraster",
    "split_hydroobjecten_at_points",
    "split_hydroobjecten_by_length",
    "split_connected_secondary_hydroobjecten",
    "waterbeheercode_from_nen3610id",
    "write_watersysteem",
]
