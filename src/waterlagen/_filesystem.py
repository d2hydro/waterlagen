"""Atomic publication with bounded retries for temporary file access failures."""

from pathlib import Path
from time import sleep

from waterlagen.logger import get_logger

logger = get_logger(__name__)


def replace_file(source: Path, target: Path) -> None:
    """Replace a file, retrying permission/sharing failures for at most 10 seconds.

    Parameters
    ----------
    source, target : pathlib.Path
        Closed temporary file and final destination. Persistent errors retain
        the original Windows exception and leave both files untouched here.
    """
    for attempt in range(11):
        try:
            source.replace(target)
            return
        except PermissionError as error:
            if attempt == 10:
                logger.error(
                    "File replacement still denied after 10 retries: %s -> %s; "
                    "winerror=%s errno=%s: %s",
                    source,
                    target,
                    getattr(error, "winerror", None),
                    error.errno,
                    error,
                )
                error.add_note(
                    f"Could not publish {source} as {target} after 10 retries. "
                    "Check open file handles, read-only attributes and folder permissions."
                )
                raise
            logger.warning(
                "File replacement denied; retry %s/10 in 1 second: %s -> %s; "
                "winerror=%s errno=%s: %s",
                attempt + 1,
                source,
                target,
                getattr(error, "winerror", None),
                error.errno,
                error,
            )
            sleep(1)
