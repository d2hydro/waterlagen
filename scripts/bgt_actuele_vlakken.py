"""Maak één GeoPackage met actuele BGT-vlaklagen voor QGIS, zonder download."""

import json
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from waterlagen.bgt.download import DEFAULT_PREDEFINED_ARCHIVE
from waterlagen.bgt.prepare import (
    SURFACE_LAYERS,
    combine_surface_layers,
    prepare_surface_layer,
    validate_surface_file,
)
from waterlagen.datastore import DataStore
from waterlagen.logger import configure_logging, get_logger

WORKERS = 2


def prepare_one(archive: Path, output: Path, name: str, log_dir: Path) -> str | None:
    """Schrijf voortgang per bronlaag naar een eigen logbestand."""
    configure_logging(log_file=log_dir / f"bgt_{name}.log", stdout=False)
    try:
        result = prepare_surface_layer(archive, output, name)
    except (OSError, RuntimeError, ValueError):
        get_logger(__name__).exception("BGT-laag mislukt: %s", name)
        raise
    return str(result) if result is not None else None


def main(data_store: DataStore | None = None) -> None:
    """Voer de conversie uit; afgeronde GeoPackages worden hergebruikt."""
    store = data_store or DataStore()
    archive = store.bgt_dir / DEFAULT_PREDEFINED_ARCHIVE
    output = store.bgt_dir
    output.mkdir(parents=True, exist_ok=True)
    target = output / "bgt.gpkg"
    if target.exists():
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
        print(f"Hergebruik: {target}", flush=True)
        return
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
    print(f"Uitvoer: {target}", flush=True)
    with tempfile.TemporaryDirectory(prefix=".bgt_lagen_", dir=output) as work:
        completed = {}
        with ProcessPoolExecutor(max_workers=WORKERS) as pool:
            tasks = {
                pool.submit(prepare_one, archive, Path(work), name, output): name
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
                print(name, status["lagen"][name], flush=True)
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
        print("Lagen samenvoegen in één ruimtelijk geïndexeerd GeoPackage", flush=True)
        configure_logging(log_file=output / "samenvoegen.log", stdout=False)
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
    print(f"Gereed: {target}", flush=True)


if __name__ == "__main__":
    main()
