"""Explicit download policy and identity checks for prepared source caches."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from waterlagen._filesystem import replace_file
from waterlagen._production import _file_identity
from waterlagen.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SourcePreparation:
    """Share download decisions with nested productions without refreshing twice."""

    refresh: bool = False
    offline: bool = False
    prepared: set[Path] = field(default_factory=set)

    def ensure(self, path: Path, download: Callable[[], object]) -> Path:
        """Reuse a source, or execute its explicit download and verify the result."""
        path = Path(path).resolve()
        if path in self.prepared:
            return path
        if path.is_file() and not self.refresh:
            logger.info("Bron hergebruiken: %s", path)
        else:
            if self.offline:
                raise FileNotFoundError(
                    f"Bron ontbreekt of moet vernieuwd worden: {path}; offline actief"
                )
            logger.info("Bron ophalen: %s", path)
            download()
            if not path.is_file():
                raise FileNotFoundError(
                    f"Download heeft het verwachte bestand niet gemaakt: {path}"
                )
        self.prepared.add(path)
        return path


def prepare_cached(
    target: Path, inputs: dict[str, Path], prepare: Callable[[], object]
) -> Path:
    """Rebuild a derived cache when inputs change; record identity after success."""
    identity = {name: _file_identity(path) for name, path in sorted(inputs.items())}
    manifest = target.with_name(target.name + ".inputs.json")
    if (
        target.is_file()
        and manifest.is_file()
        and json.loads(manifest.read_text(encoding="utf-8")) == identity
    ):
        logger.info("Voorbereide bron hergebruiken: %s", target)
        return target
    logger.info("Bron voorbereiden: %s", target)
    prepare()
    if not target.is_file():
        raise FileNotFoundError(f"Voorbereide bron ontbreekt: {target}")
    temporary = manifest.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(identity, indent=2), encoding="utf-8")
    replace_file(temporary, manifest)
    return target


def source_options(
    preparation: SourcePreparation | None,
    *,
    refresh_sources: bool,
    offline: bool,
    resume: bool,
    overwrite: bool,
) -> SourcePreparation:
    """Reject refresh for existing runs before touching source files."""
    preparation = preparation or SourcePreparation(refresh_sources, offline)
    if preparation.refresh and (resume or overwrite or preparation.offline):
        raise ValueError(
            "Bronnen vernieuwen vereist een nieuwe run zonder --resume, --overwrite of --offline"
        )
    return preparation
