"""Drie onafhankelijke regressievoorbeelden met blijvende, inspecteerbare uitvoer.

Voer vanuit de repositoryroot uit (geen downloads of productiegegevens nodig):
  pixi run --as-is --environment afwateringseenheden python -B reviewcases/review-e7db72f/reproduce.py optional-water
  pixi run --as-is --environment afwateringseenheden python -B reviewcases/review-e7db72f/reproduce.py crossing
  pixi run --as-is --environment afwateringseenheden python -B reviewcases/review-e7db72f/reproduce.py empty-culverts

Iedere uitvoering maakt een nieuwe map output/<case>-<tijdstip>. Open vergelijking.png,
resultaat.json en de GeoPackages in die map. Bij de waternetvoorbeelden bevat
berekening/waterlopen_duikers/*.tif de echte uitvoer: behandeling, broncode,
doeluitsluiting en ondiepe branddiepte (banden 1 t/m 4). controle.gpkg bevat de
duikerclassificatie. Dit test de voorbereiding, niet de uiteindelijke afvoergebieden.
De assertions toetsen correct gedrag en falen op de onderzochte commit e7db72f.
Resultaten worden VOOR de assertions opgeslagen. Bestaande bestanden blijven intact.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point, box

from waterlagen._geopandas import read_file
from waterlagen.afwateringseenheden.config import BrandlagenConfig
from waterlagen.afwateringseenheden.sources import WatersysteemSources
from waterlagen.afwateringseenheden.waternet import prepare_waternet, read_waternet
from waterlagen.afwateringseenheden.workflow import prepare_watersysteem
from waterlagen.raster.grid import RasterGrid

CRS = "EPSG:28992"


def frame(geometries=()) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=list(geometries), crs=CRS)


def save_layer(data: gpd.GeoDataFrame, path: Path, layer: str) -> None:
    data.to_file(path, layer=layer, driver="GPKG", index=False, engine="pyogrio")


def save_result(output: Path, result: dict) -> None:
    repository = Path(__file__).resolve().parents[2]

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=repository, text=True, encoding="utf-8"
        ).strip()

    result["uitvoering"] = {
        "commit": git("rev-parse", "HEAD"),
        "basis_main": git("merge-base", "main", "HEAD"),
        "lokale_wijzigingen_bestaande_bestanden": git(
            "status", "--short", "--untracked-files=no"
        ),
        "omgeving": "pixi --as-is --environment afwateringseenheden",
        "python": sys.version,
        "geopandas": gpd.__version__,
        "crs": CRS,
        "tijd_utc": datetime.now(UTC).isoformat(),
    }
    (output / "resultaat.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
    print(f"Bekijk resultaten: {output}", flush=True)


def plot_waternet(
    output: Path,
    data: WatersysteemSources,
    optional: gpd.GeoDataFrame,
    treatment: np.ndarray,
    expected_depth: float,
    actual_depth: float,
) -> None:
    from matplotlib import pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch

    colors = ["#f4f4f4", "#12498a", "#377eb8", "#55c8be", "#bdbdbd"]
    labels = ["Geen inbranding", "Primair", "Diep", "Ondiep", "Uitgesloten"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 5.5), layout="constrained")
    for features, color, label in (
        (data.primary, colors[1], "HYDAMO primair"),
        (data.secondary, colors[2], "HYDAMO secundair"),
        (optional.loc[optional.rol.eq("water")], "#159c70", "OSM-water"),
    ):
        if not features.empty:
            features.plot(ax=axes[0], color=color, linewidth=3, label=label)
    optional.loc[optional.rol.eq("duiker")].boundary.plot(
        ax=axes[0], color="#dc6b14", linewidth=2, label="BGT-duikervlak"
    )
    axes[0].legend(loc="lower left", fontsize=8)
    axes[0].set_title("Synthetische invoer")
    axes[1].imshow(
        treatment,
        origin="upper",
        extent=(0, 40, 0, 40),
        cmap=ListedColormap(colors),
        norm=BoundaryNorm(np.arange(-0.5, 5), 5),
        interpolation="nearest",
    )
    axes[1].legend(
        handles=[
            Patch(facecolor=color, label=label) for color, label in zip(colors, labels)
        ],
        loc="lower left",
        fontsize=8,
    )
    axes[1].set_title("Berekende waternetbehandeling (2 m raster)")
    for axis in axes:
        axis.plot(15, 21, "x", color="#c30028", markersize=9, markeredgewidth=2)
        axis.annotate(
            "meetpunt (15, 21)",
            (15, 21),
            xytext=(3, 31),
            arrowprops={"arrowstyle": "->"},
            fontsize=9,
        )
        axis.set(
            xlim=(0, 40), ylim=(0, 40), xlabel="x (m)", ylabel="y (m)", aspect="equal"
        )
    fig.suptitle(
        f"Verlaging bij meetpunt: verwacht {expected_depth:g} m, berekend {actual_depth:g} m\n"
        f"{CRS} | verlaging stuurt afstroming; geen werkelijke bodemhoogte"
    )
    fig.savefig(output / "vergelijking.png", dpi=150)
    plt.close(fig)


def waternet_case(output: Path, case: str) -> None:
    if case == "optional-water":
        primary = frame([LineString([(37, 1), (37, 39)])])
        secondary = frame()
        extra = frame(
            [
                LineString([(1, 21), (11, 21)]),
                LineString([(21, 21), (37, 21)]),
                box(10, 20, 22, 22),
            ]
        )
        roles, origins = ["water", "water", "duiker"], ["osm", "osm", "bgt"]
        expected_treatment, expected_depth, expected_class = 3, 10.0, "aanvoer"
        reason = (
            "Twee OSM-waterlopen sluiten aan op de uiteinden van een BGT-duikervlak. "
            "De aanvullende duiker hoort zijn eigen brandwaarde -10 m te gebruiken; "
            "de verbinding mag geen diepe HYDAMO-route worden. "
            "Zie docs/produceren/afwateringseenheden.md: Waterlopen en duikers."
        )
    else:
        primary = frame()
        secondary = frame([LineString([(21, 1), (21, 39)])])
        extra = frame([box(10, 20, 32, 22)])
        roles, origins = ["duiker"], ["bgt"]
        expected_treatment, expected_depth, expected_class = 0, 0.0, "controle"
        reason = (
            "Een doorgaande secundaire lijn kruist het midden van een BGT-duikervlak; "
            "geen waterloopeindpunt sluit erop aan. Alleen kruisen is volgens "
            "docs/produceren/afwateringseenheden.md niet genoeg. Het meetpunt ligt "
            "op de duiker, buiten de secundaire lijn, en mag niet worden ingebrand."
        )
    extra["rol"] = roles
    extra["bron"] = origins
    extra["broncode"] = np.arange(3, len(extra) + 3)
    extra["bronbestand"] = "invoer.gpkg"
    extra["bronlaag"] = "aanvullend"
    extra["bron_fid"] = range(len(extra))
    extra["brandwaarde"] = -10.0
    extra["prioriteit"] = 1
    data = WatersysteemSources(
        primary, secondary, primary.copy(), frame(), tertiary=frame()
    )
    network = output / "invoer.gpkg"
    save_layer(primary, network, "primair")
    save_layer(secondary, network, "secundair")
    save_layer(extra, network, "aanvullend")
    # prepare_waternet gebruikt dit bestand alleen voor cache-identiteit; de echte
    # geometrie-invoer wordt rechtstreeks via data en extra doorgegeven.
    grid = RasterGrid.from_bounds((0, 0, 40, 40), resolution=2, crs=CRS)
    prepare_waternet(data, extra, [grid], network, BrandlagenConfig())
    treatment, codes, excluded, _, shallow = read_waternet(network, grid)
    col, row = ~grid.transform * (15, 21)
    cell = int(row), int(col)
    actual_treatment = int(treatment[cell])
    actual_depth = float(shallow[cell]) if actual_treatment == 3 else 0.0
    classified = read_file(output / "controle.gpkg", layer="duikers_waternet")
    actual_class = str(classified.behandeling.iloc[0])
    probe = frame([Point(15, 21)])
    probe["verwacht_verlaging_m"] = expected_depth
    probe["berekend_verlaging_m"] = actual_depth
    save_layer(probe, output / "vergelijking.gpkg", "meetpunt")
    plot_waternet(output, data, extra, treatment, expected_depth, actual_depth)
    save_result(
        output,
        {
            "testcase": case,
            "onderbouwing": reason,
            "raster": {
                "bounds": [0, 0, 40, 40],
                "resolutie_m": 2,
                "meetpunt": [15, 21],
            },
            "verwacht": {
                "classificatie": expected_class,
                "behandeling": expected_treatment,
                "verlaging_meetpunt_m": expected_depth,
            },
            "berekend": {
                "classificatie": actual_class,
                "behandeling": actual_treatment,
                "verlaging_meetpunt_m": actual_depth,
                "broncode": int(codes[cell]),
                "uitgesloten_als_doel": bool(excluded[cell]),
                "reden_classificatie": str(classified.reden.iloc[0]),
            },
        },
    )
    assert actual_treatment == expected_treatment, (
        f"Meetpunt (15, 21): behandeling {actual_treatment}, verwacht {expected_treatment}; "
        f"verlaging {actual_depth} m in plaats van {expected_depth} m. Zie {output}"
    )
    assert actual_depth == expected_depth
    assert actual_class == expected_class


def empty_culverts_case(output: Path) -> None:
    from matplotlib import pyplot as plt

    hydro = frame([LineString([(0, 0), (20, 0)])])
    hydro.index = [42]  # Geen bron_id/globalid/code; bijvoorbeeld na een selectie.
    empty = frame()
    baseline = prepare_watersysteem(hydro, empty).hydroobject_segmenten
    actual = prepare_watersysteem(
        hydro, empty, duikersifonhevel=empty
    ).hydroobject_segmenten
    # De invoerindex staat apart in het GPKG; het script herstelt hem hierboven.
    saved_input = hydro.copy()
    saved_input["invoerindex"] = hydro.index
    save_layer(saved_input, output / "vergelijking.gpkg", "invoer")
    save_layer(hydro, output / "vergelijking.gpkg", "verwachte_geometrie")
    save_layer(baseline, output / "vergelijking.gpkg", "zonder_duikerparameter")
    save_layer(actual, output / "vergelijking.gpkg", "met_lege_duikers")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3), layout="constrained")
    for axis, features, title in (
        (axes[0], hydro, "Verwacht: 1 segment van 20 m"),
        (axes[1], actual, f"Berekend: {len(actual)} segmenten"),
    ):
        if features.empty:
            axis.text(10, 0, "De waterloop is verdwenen", ha="center", color="#c30028")
        else:
            features.plot(ax=axis, color="#12498a", linewidth=4)
        axis.set(
            xlim=(-2, 22),
            ylim=(-4, 4),
            xlabel="x (m)",
            ylabel="y (m)",
            aspect="equal",
            title=title,
        )
    fig.suptitle(f"Lege duikerinvoer mag bestaande waterloop niet verwijderen | {CRS}")
    fig.savefig(output / "vergelijking.png", dpi=150)
    plt.close(fig)
    save_result(
        output,
        {
            "testcase": "empty-culverts",
            "onderbouwing": "prepare_watersysteem documenteert index als terugval voor bron_id. "
            "Een lege duikerlaag mag de geometrie niet veranderen.",
            "invoer": {"index": [42], "identificatievelden": [], "aantal_duikers": 0},
            "verwacht": {"segmenten": 1, "lengte_m": 20.0},
            "zonder_duikerparameter": {
                "segmenten": len(baseline),
                "bron_id": baseline.bron_id.tolist(),
            },
            "berekend": {
                "segmenten": len(actual),
                "lengte_m": float(actual.length.sum()),
                "bron_id": actual.bron_id.tolist(),
            },
        },
    )
    assert len(actual) == 1, (
        f"Lege duikerlaag verwijdert waterloop: {len(actual)} segmenten; zie {output}"
    )
    assert actual.geometry.iloc[0].equals(hydro.geometry.iloc[0])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "case", choices=["optional-water", "crossing", "empty-culverts"]
    )
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = Path(__file__).resolve().parent / "output" / f"{args.case}-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    os.environ["MPLCONFIGDIR"] = str(output / "matplotlib")
    os.environ["MPLBACKEND"] = "Agg"
    if args.case == "empty-culverts":
        empty_culverts_case(output)
    else:
        waternet_case(output, args.case)


if __name__ == "__main__":
    main()
