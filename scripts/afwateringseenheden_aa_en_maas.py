"""Compatibility entry point for the packaged Aa en Maas workflow."""

import multiprocessing

from waterlagen.afwateringseenheden.production import produce_afwateringseenheden


def main() -> None:
    """Produce Aa en Maas using the configured DataStore and default settings."""
    produce_afwateringseenheden()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
