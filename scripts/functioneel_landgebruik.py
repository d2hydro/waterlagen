"""Landelijke productie: bronnen hergebruiken, tegels opnieuw maken, COG hergebruiken."""

import argparse
import hashlib
import json
import shutil
from dataclasses import replace
from datetime import datetime
from multiprocessing import freeze_support
from pathlib import Path

import pyogrio

from waterlagen.datastore import DataStore
from waterlagen.functioneel_landgebruik import (
    FunctioneelLandgebruikSources,
    bouw_functioneel_landgebruik_tiles,
)
from waterlagen.functioneel_landgebruik.landgebruikstabel import (
    DEFAULT_MAPPING_CSV,
    load_landuse_table,
)
from waterlagen.functioneel_landgebruik.legenda import write_qgis_style
from waterlagen.logger import configure_logging, get_logger
from waterlagen.raster.tiles import build_tiles
from waterlagen.raster.vrt import create_cog_file, create_vrt_file

# Instellingen voor landelijke productie.
WORKERS = 32
RESOLUTION_M = 0.5
TEGELGROOTTE_M = 5000
UITVOERMAP = "functioneel_landgebruik_20260925_actuele_bgt"
BGT_BESTAND = "bgt.gpkg"
LANDGEBRUIK_CSV = DEFAULT_MAPPING_CSV
TEGELS_OVERSCHRIJVEN = True
COG_OVERSCHRIJVEN = False  # Bestaande landelijke TIFF behouden.
CONTROLE_OPSLAAN = True  # Alleen NoData-vlakken met bron en reden.
# Bestaande bronbestanden en het tegelrooster worden hergebruikt.


def main(
    data_store: DataStore | None = None,
    *,
    mapping_csv: Path | None = None,
    bgt_path: Path | None = None,
) -> Path:
    """Voer de landelijke productie uit; bgt_path gebruikt voorbereide BGT zonder download."""
    store = data_store or DataStore()
    mapping_csv = Path(mapping_csv or LANDGEBRUIK_CSV)
    table = load_landuse_table(mapping_csv)
    output = store.processed_data_dir / UITVOERMAP
    output.mkdir(parents=True, exist_ok=True)
    configure_logging(log_file=output / "productie.log", stdout=False)
    logger = get_logger(__name__)
    csv_path = output / "landgebruik_met_code.csv"
    if csv_path.exists() and csv_path.read_bytes() != mapping_csv.read_bytes():
        raise ValueError("Runfolder bevat een andere CSV; kies een nieuwe uitvoermap.")
    if mapping_csv.resolve() != csv_path.resolve():
        shutil.copyfile(mapping_csv, csv_path)
    status = {
        "started": datetime.now().astimezone().isoformat(),
        "output": str(output),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "resolution_m": RESOLUTION_M,
        "workers": WORKERS,
        "rwzi": "niet uitgevoerd: bedrijfsstatusbron ontbreekt",
        "drinkwater": "niet uitgevoerd: terreinbron ontbreekt",
    }

    def stage(name: str) -> None:
        status["stage"] = name
        status["updated"] = datetime.now().astimezone().isoformat()
        temporary = output / "status.tmp.json"
        temporary.write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(output / "status.json")
        logger.info("%s", name)

    try:
        stage("Landelijk tegelrooster maken")
        tiles = build_tiles(
            target_path=output / "tiles.gpkg",
            tile_size_m=TEGELGROOTTE_M,
            overwrite=False,
        )
        status["tile_count"] = int(pyogrio.read_info(tiles, layer="tiles")["features"])
        bgt = Path(bgt_path) if bgt_path is not None else store.bgt_dir / BGT_BESTAND
        featuretypes = [
            "waterdeel",
            "wegdeel",
            "ondersteunendwegdeel",
            "begroeidterreindeel",
            "onbegroeidterreindeel",
        ]
        stage("Voorbereide actuele BGT gebruiken, inclusief aanvullende controlelagen")
        if not bgt.is_file():
            raise FileNotFoundError(
                f"BGT-bestand ontbreekt: {bgt}. "
                "Voer eerst scripts/bgt_actuele_vlakken.py uit."
            )
        for name in featuretypes:
            columns = set(pyogrio.read_info(bgt, layer="bgt_" + name)["fields"])
            if not {"bgt-status", "eindRegistratie", "objectEindTijd"}.issubset(
                columns
            ):
                raise ValueError("Einddatumvelden ontbreken in " + name)
        sources = replace(
            FunctioneelLandgebruikSources.from_datastore(store), bgt_gpkg=bgt
        )
        status["sources"] = {
            name: str(path) if path else None for name, path in vars(sources).items()
        }
        stage("Landelijke rastertegels berekenen")
        result = bouw_functioneel_landgebruik_tiles(
            target_dir=output / "tiles",
            tiles_path=tiles,
            workers=WORKERS,
            resolution_m=RESOLUTION_M,
            sources=sources,
            download_missing_sources=False,
            overwrite=TEGELS_OVERSCHRIJVEN,
            mapping_csv=csv_path,
            diagnostics_path=output / "nodata.gpkg" if CONTROLE_OPSLAAN else None,
        )
        status["completed_tiles"] = len(result)
        stage("VRT samenstellen")
        vrt = create_vrt_file(
            vrt_file=output / "functioneel_landgebruik.vrt", directory=output / "tiles"
        )
        stage("Landelijke GeoTIFF maken")
        tif = create_cog_file(
            vrt_file=vrt,
            cog_file=output / "functioneel_landgebruik.tif",
            overwrite=COG_OVERSCHRIJVEN,
        )
        write_qgis_style(tif, table)
        status["result"] = str(tif)
        stage("Voltooid")
        return tif
    except Exception as error:
        status["error"] = repr(error)
        stage("Mislukt")
        raise


if __name__ == "__main__":
    freeze_support()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mapping-csv", type=Path, help="Eigen UTF-8-codetabel met puntkomma's."
    )
    arguments = parser.parse_args()
    main(mapping_csv=arguments.mapping_csv)
