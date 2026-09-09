"""PCRaster integration for afwateringseenheden calculations."""

from types import ModuleType


def require_pcraster() -> ModuleType:
    """Import PCRaster or raise an actionable installation error."""
    try:
        import pcraster
    except ImportError as exc:
        raise RuntimeError(
            "PCRaster is required for afwateringseenheden. "
            "Run `pixi run --environment afwateringseenheden python ...`."
        ) from exc
    return pcraster