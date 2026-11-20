"""Vergrendel een run zolang het productieproces leeft."""

import errno
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from waterlagen.logger import get_logger

logger = get_logger(__name__)
_MARKER = b"waterlagen-run-lock-v2\n"


@contextmanager
def _guard(path: Path, *, read_only: bool = False) -> Iterator[bool]:
    # Dit bestand blijft bestaan, zodat alle processen hetzelfde slot gebruiken.
    with (path / ".run.guard").open("rb" if read_only else "a+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            yield False
            return
        try:
            yield True
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _legacy_marker(marker: Path) -> bool:
    try:
        return marker.read_bytes() != _MARKER
    except FileNotFoundError:
        return False


def run_is_locked(path: Path) -> bool:
    """Controleer het processlot; oude slotbestanden blijven beschermd."""
    if not (path / ".run.guard").exists():
        return (path / ".run.lock").exists()
    with _guard(path, read_only=True) as acquired:
        return not acquired or _legacy_marker(path / ".run.lock")


@contextmanager
def production_lock(path: Path) -> Iterator[None]:
    """Houd het processlot vast; na procesdood kan dezelfde run verder."""
    marker = path / ".run.lock"
    with _guard(path) as acquired:
        if not acquired:
            raise ValueError(
                f"Runfolder '{path}' is vergrendeld; de productie draait nog."
            )
        while True:
            try:
                # Exclusief aanmaken beschermt ook tegen een draaiende oude versie.
                with marker.open("xb") as handle:
                    handle.write(_MARKER)
                break
            except FileExistsError as error:
                try:
                    content = marker.read_bytes()
                except FileNotFoundError:
                    # De vorige productie is net klaar; claim het slot opnieuw.
                    continue
                if content != _MARKER:
                    raise ValueError(
                        f"Runfolder '{path}' is vergrendeld met een oud slotbestand. "
                        f"Verwijder '{marker}' alleen na controle dat de productie is gestopt."
                    ) from error
                logger.info("Runmap opnieuw vergrendeld na onderbreking: %s", path)
                break
        try:
            yield
        finally:
            marker.unlink(missing_ok=True)
