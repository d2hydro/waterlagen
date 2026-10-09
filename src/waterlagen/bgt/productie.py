"""Maak één GeoPackage met actuele BGT-vlaklagen voor QGIS, zonder download."""

import json
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from multiprocessing import get_context
from pathlib import Path

from waterlagen._run_logging import executor_logging
from waterlagen.bgt.download import DEFAULT_PREDEFINED_ARCHIVE
from waterlagen.bgt.prepare import (
    SURFACE_LAYERS,
    combine_surface_layers,
    prepare_surface_layer,
    validate_surface_file,
)
from waterlagen.datastore import DataStore
from waterlagen.logger import get_logger

WORKERS = 2


def _prepare_one(archive: Path, output: Path, name: str) -> str | None:
    """Prepare one BGT layer with caller-owned logging."""
    try:
        result = prepare_surface_layer(archive, output, name)
    except (OSError, RuntimeError, ValueError):
        get_logger(__name__).exception("BGT-laag mislukt: %s", name)
        raise
    return str(result) if result is not None else None


def main(
    data_store: DataStore | None = None,
    *,
    overwrite: bool = False,
    workers: int = WORKERS,
) -> Path:
    """Convert cached BGT GML Light to one validated GeoPackage.

    Parameters
    ----------
    data_store : DataStore, optional
        Location of the downloaded BGT archive and prepared GeoPackage.
    overwrite : bool, optional
        Rebuild instead of validating and reusing completed output.
    workers : int, optional
        Concurrent layer conversions, default 2.

    Returns
    -------
    pathlib.Path
        Prepared ``bgt.gpkg``. No download is performed by this function.
    """
    store = data_store or DataStore()
    archive = store.bgt_dir / DEFAULT_PREDEFINED_ARCHIVE
    output = store.bgt_dir
    output.mkdir(parents=True, exist_ok=True)
    target = output / "bgt.gpkg"
    if target.exists() and not overwrite:
        previous = json.loads(
            (output / "bgt_actuele_vlakken.status.json").read_text(encoding="utf-8")
        )
        if previous["status"] != "Gereed" or set(previous["lagen"]) != set(
            SURFACE_LAYERS
        ):
            raise ValueError("Bestaande BGT heeft geen volledige gereedmelding.")
        for name, result in previous["lagen"].items():
            if not result.startswith("Overgeslagen:"):
                validate_surface_file(target, "bgt_" + name)
        get_logger(__name__).info("Hergebruik: %s", target)
        return target
    if not archive.is_file():
        raise FileNotFoundError(archive)
    status = {
        "bron": str(archive),
        "gestart": datetime.now().astimezone().isoformat(),
        "status": "Bezig",
        "lagen": {name: "Wacht op verwerking" for name in SURFACE_LAYERS},
    }

    def save_status() -> None:
        temporary = output / "bgt_actuele_vlakken.status.tmp.json"
        temporary.write_text(
            json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temporary.replace(output / "bgt_actuele_vlakken.status.json")

    save_status()
    get_logger(__name__).info("Uitvoer: %s", target)
    with tempfile.TemporaryDirectory(prefix=".bgt_lagen_", dir=output) as work:
        completed = {}
        with ProcessPoolExecutor(
            max_workers=workers, mp_context=get_context("spawn"), **executor_logging()
        ) as pool:
            tasks = {
                pool.submit(_prepare_one, archive, Path(work), name): name
                for name in SURFACE_LAYERS
            }
            for task in as_completed(tasks):
                name = tasks[task]
                try:
                    result = task.result()
                    status["lagen"][name] = (
                        "Gereed" if result else "Overgeslagen: geen actuele vlakken"
                    )
                    if result is not None:
                        completed[name] = Path(result)
                except (OSError, RuntimeError, ValueError) as error:
                    status["lagen"][name] = f"Fout: {error}"
                get_logger(__name__).info("BGT %s: %s", name, status["lagen"][name])
                save_status()
        status["status"] = (
            "Gereed"
            if not any(value.startswith("Fout:") for value in status["lagen"].values())
            else "Gereed met fouten"
        )
        if status["status"] != "Gereed":
            save_status()
            raise RuntimeError(
                f"Niet alle lagen zijn gelukt; zie {output / 'bgt_actuele_vlakken.status.json'}"
            )
        status["status"] = "Lagen samenvoegen"
        save_status()
        get_logger(__name__).info("BGT-lagen samenvoegen: %s", target)
        try:
            combine_surface_layers(
                [completed[name] for name in SURFACE_LAYERS if name in completed],
                target,
            )
        except (OSError, RuntimeError, ValueError) as error:
            status["status"] = f"Samenvoegen mislukt: {error}"
            save_status()
            raise
    status["status"] = "Gereed"
    status["uitvoer"] = str(target)
    status["afgerond"] = datetime.now().astimezone().isoformat()
    save_status()
    get_logger(__name__).info("Gereed: %s", target)
    return target
