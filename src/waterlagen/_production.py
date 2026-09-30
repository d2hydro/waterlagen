"""Shared output folders and explicit reuse for production entry points."""

import argparse
import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from xml.etree import ElementTree

from waterlagen.logger import get_logger

logger = get_logger(__name__)


def default_run_id() -> str:
    """Return a UTC production timestamp, suitable as a directory name."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def validate_run_options(run_id: str | None, *, resume: bool, overwrite: bool) -> None:
    """Reject implicit reuse and ambiguous or unsafe folder names."""
    if resume and overwrite:
        raise ValueError("Gebruik --resume óf --overwrite, niet beide")
    if (resume or overwrite) and run_id is None:
        raise ValueError("--resume en --overwrite vereisen een expliciete --run-id")
    if run_id is not None:
        reserved = {"CON", "PRN", "AUX", "NUL"}
        reserved.update(
            f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
        )
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", run_id)
            or run_id.upper() in reserved
        ):
            raise ValueError(
                "Run-ID: gebruik 1–100 letters, cijfers, underscores of koppeltekens; geen pad of gereserveerde naam"
            )


def add_run_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the same production-folder controls to each script's CLI."""
    parser.add_argument(
        "--run-id", help="Runnaam; standaard een nieuwe UTC-tijdstempel"
    )
    reuse = parser.add_mutually_exclusive_group()
    reuse.add_argument(
        "--resume",
        action="store_true",
        help="Hervat een bestaande, compatibele --run-id",
    )
    reuse.add_argument(
        "--overwrite",
        action="store_true",
        help="Bereken uitvoer van een bestaande, compatibele --run-id opnieuw",
    )


def _file_identity(path: Path, ancestors: tuple[Path, ...] = ()) -> dict[str, object]:
    """Record local input identity without hashing large geospatial datasets."""
    path = path.resolve()
    identity: dict[str, object] = {"path": str(path)}
    if not path.is_file():
        identity["exists"] = False
        return identity
    if path.suffix.lower() == ".vrt":
        if path in ancestors:
            raise ValueError(f"Cyclische VRT-bronverwijzing: {path}")
        content = path.read_bytes()
        identity["sha256"] = hashlib.sha256(content).hexdigest()
        references = []
        for element in ElementTree.fromstring(content).iter("SourceFilename"):
            reference = Path(element.text or "")
            if element.get("relativeToVRT") == "1":
                reference = path.parent / reference
            references.append(_file_identity(reference, (*ancestors, path)))
        identity["sources"] = references
    else:
        stat = path.stat()
        identity.update(size=stat.st_size, mtime_ns=stat.st_mtime_ns)
    return identity


@dataclass
class ProductionRun:
    """One run's directory and provenance; inputs are checked before output reuse."""

    path: Path
    metadata: dict[str, object]

    def _save(self) -> None:
        self.metadata["updated"] = datetime.now(UTC).isoformat()
        temporary = self.path / "run.tmp.json"
        temporary.write_text(
            json.dumps(self.metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temporary.replace(self.path / "run.json")

    def record_inputs(self, sources: dict[str, Path | None]) -> None:
        """Validate paths, sizes and modification times before producing outputs.

        VRTs use content hashes and include their referenced local files.
        Missing optional inputs are recorded explicitly. A changed input requires
        a new run ID, including when outputs would otherwise be overwritten.
        """
        inputs = {
            name: _file_identity(path) if path is not None else None
            for name, path in sorted(sources.items())
        }
        previous = self.metadata.get("inputs")
        if previous is not None and previous != inputs:
            raise ValueError(
                f"Runfolder '{self.path}' heeft andere bronbestanden. Kies een nieuwe --run-id; bestaande uitvoer is niet hergebruikt."
            )
        self.metadata["inputs"] = inputs
        self._save()


@contextmanager
def production_run(
    processed_data_dir: Path,
    dataset: str,
    scope: str,
    *,
    run_id: str | None = None,
    resume: bool = False,
    overwrite: bool = False,
    parameters: dict[str, object],
) -> Iterator[ProductionRun]:
    """Create or explicitly reuse ``dataset/scope/run_id`` under processed data.

    Reuse requires matching parameters, software version and recorded inputs.
    Overwrite permits rebuilding outputs, not changing a run's identity. Existing
    directories without run metadata are never adopted. No outputs are deleted.
    """
    validate_run_options(run_id, resume=resume, overwrite=overwrite)
    run_id = run_id or default_run_id()
    path = (processed_data_dir / dataset / scope / run_id).resolve()
    identity = {
        "dataset": dataset,
        "scope": scope,
        "run_id": run_id,
        "software_version": version("waterlagen"),
        "parameters": parameters,
    }
    if resume or overwrite:
        if not (path / "run.json").is_file():
            raise ValueError(
                f"Runfolder '{path}' heeft geen run.json. Kies een nieuwe --run-id; oude uitvoermappen worden niet automatisch gemigreerd."
            )
    else:
        try:
            path.mkdir(parents=True, exist_ok=False)
        except FileExistsError as error:
            raise ValueError(
                f"Runfolder '{path}' bestaat al. Kies een andere --run-id, of gebruik --resume of --overwrite met dezelfde instellingen."
            ) from error
    lock = path / ".run.lock"
    try:
        lock.touch(exist_ok=False)
    except FileExistsError as error:
        raise ValueError(
            f"Runfolder '{path}' is vergrendeld. Verwijder '{lock}' alleen als er geen productie meer actief is."
        ) from error
    try:
        if resume or overwrite:
            metadata = json.loads((path / "run.json").read_text(encoding="utf-8"))
            if any(metadata.get(key) != value for key, value in identity.items()):
                raise ValueError(
                    f"Runfolder '{path}' heeft andere instellingen, software of mapping-CSV. Kies een nieuwe --run-id."
                )
        else:
            metadata = {**identity, "created": datetime.now(UTC).isoformat()}
        run = ProductionRun(path, metadata)
        run.metadata.update(
            status="running",
            mode="overwrite" if overwrite else "resume" if resume else "new",
        )
        run.metadata.pop("error", None)
        run._save()
        logger.info("Productie-uitvoermap: %s", path)
        try:
            yield run
        except BaseException as error:
            run.metadata.update(status="failed", error=str(error))
            run._save()
            raise
        else:
            run.metadata["status"] = "complete"
            run._save()
    finally:
        lock.unlink()
