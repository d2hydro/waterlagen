"""Schrijf alleen de lege rastercellen als vlakken, met een reden.

- Een open BAG-keuze verklaart het bewust leegmaken van een cel.
- Bij andere gaten worden de gevonden bronuitsluitingen vermeld.
- Zonder specifieke aanwijzing blijft de reden algemeen.
"""

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio as rio
from rasterio.features import geometry_mask, shapes
from rasterio.windows import Window
from shapely.geometry import box, shape

from waterlagen import _geopandas as wgpd
from waterlagen._crs import same_crs
from waterlagen._downloads import validate_geopackage
from waterlagen.logger import get_logger

logger = get_logger(__name__)

LAYER = "nodata"
FORMAT_VERSION = "3"
NO_SOURCE_REASON = "Geen bron vult deze plek."
UNUSED_BGT_LAYERS = (
    "bgt_ondersteunendwaterdeel",
    "bgt_overbruggingsdeel",
    "bgt_tunneldeel",
    "bgt_kunstwerkdeel",
    "bgt_overigbouwwerk",
    "bgt_scheiding",
    "bgt_overigescheiding",
    "bgt_gebouwinstallatie",
    "bgt_vegetatieobject",
    "bgt_ongeclassificeerdobject",
    "bgt_pand",
    "bgt_functioneelgebied",
)


@dataclass
class LanduseDiagnostics:
    """Verzamel alleen uitzonderingen uit de verwerking van één rastertegel."""

    parts: list[gpd.GeoDataFrame] = field(default_factory=list)

    def add(
        self,
        data: gpd.GeoDataFrame,
        *,
        source: str,
        layer: str,
        source_path: Path,
        stage: str,
        reason: str | pd.Series,
        value_column: str | None = None,
        id_column: str | None = None,
        writes_nodata: bool = False,
        details: str | pd.Series = "",
    ) -> None:
        """Bewaar brongegevens en uitleg; verander de bronobjecten niet."""
        if data.empty:
            return
        records = data[["geometry"]].copy()
        records["bron"] = source
        records["bronlaag"] = layer
        records["bronveld"] = value_column or ""
        records["bronbestand"] = str(source_path)
        records["id_veld"] = id_column or "fid"
        records["object_id"] = (
            data[id_column].astype("string")
            if id_column is not None
            else data.index.astype(str)
        )
        records["bronwaarde"] = (
            data[value_column].astype("string") if value_column is not None else ""
        )
        records["stap"] = stage
        records["reden"] = reason
        records["werking"] = "schrijft NoData" if writes_nodata else "overgeslagen"
        records["toelichting"] = details
        self.parts.append(records)

    def add_unclassified_buildings(
        self, buildings: gpd.GeoDataFrame, *, source_path: Path, layer: str
    ) -> None:
        """Neem open pandkeuzes pas na bijzondere gebouwen en gemalen over."""
        unresolved = buildings.loc[buildings["code"].eq(0)]
        reasons = unresolved["reden_klasse"].copy()
        # Bijzondere gebouwen kunnen een eigen conflict hebben; behoud die reden.
        ordinary = unresolved["bijzondere_koppelingen"].fillna("").eq("")
        function_open = ordinary & unresolved["functiekeuze_status"].eq(
            "nog te beoordelen"
        )
        reasons.loc[function_open] = unresolved.loc[function_open, "reden_functiekeuze"]
        floors_open = (
            ordinary
            & unresolved["functiekeuze_status"].eq("gekozen")
            & unresolved["berekend_aantal_bouwlagen"].isna()
            & ~unresolved["gekozen_pandfunctie"].eq("overige gebruiksfunctie")
        )
        reasons.loc[floors_open] = unresolved.loc[floors_open, "reden_bouwlagen"]
        self.add(
            unresolved,
            source="BAG",
            layer=layer,
            source_path=source_path,
            stage="Gebouwklasse",
            reason=reasons,
            id_column="identificatie",
            value_column="alle_bag_gebruiksdoelen",
            writes_nodata=True,
            details=unresolved["bron_vbo_overzicht"],
        )

    def write(
        self,
        target_path: Path,
        *,
        raster_path: Path,
        top10nl_gpkg: Path | None = None,
        bgt_gpkg: Path | None = None,
    ) -> Path:
        """Vervang de controle atomair door één laag met NoData en reden."""
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".lgb_controle_", dir=target_path.parent
        ) as work:
            temporary = Path(work) / target_path.name
            with rio.open(raster_path) as raster:
                records = _reason_records(self.parts, raster.crs)
                terrains = _unused_terrain(top10nl_gpkg, raster.bounds, raster.crs)
                unused_bgt = _unused_bgt(bgt_gpkg, raster.bounds, raster.crs)
                _write_layer(
                    _empty_layer(raster.crs),
                    temporary,
                    metadata=_raster_metadata(raster_path),
                )
                # Blokken begrenzen het geheugengebruik bij landelijke productie.
                for row in range(0, raster.height, 2048):
                    for col in range(0, raster.width, 2048):
                        window = Window(
                            col,
                            row,
                            min(2048, raster.width - col),
                            min(2048, raster.height - row),
                        )
                        nodata = raster.read(1, window=window) == raster.nodata
                        if not nodata.any():
                            continue
                        indices = records.sindex.query(
                            box(*raster.window_bounds(window)), predicate="intersects"
                        )
                        selected = records.iloc[indices]
                        polygons = _nodata_polygons(
                            nodata,
                            selected,
                            raster.window_transform(window),
                            raster.crs,
                            terrains=terrains,
                            unused_bgt=unused_bgt,
                        )
                        _write_layer(polygons, temporary, append=True)
            validate_geopackage(temporary)
            temporary.replace(target_path)
        logger.info("Controle-uitvoer geschreven: %s", target_path)
        return target_path


def _empty_layer(crs) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"bron": pd.Series(dtype="string"), "reden": pd.Series(dtype="string")},
        geometry=gpd.GeoSeries([], crs=crs),
    )


def _reason_records(parts: list[gpd.GeoDataFrame], crs) -> gpd.GeoDataFrame:
    """Vat bronuitsluitingen samen; bronattributen blijven buiten de uitvoer."""
    if not parts:
        result = _empty_layer(crs)
        result["direct"] = pd.Series(dtype="bool")
        return result
    data = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True))
    if not same_crs(data.crs, crs):
        raise ValueError("Controleobjecten en raster moeten hetzelfde CRS hebben.")
    data = data.loc[data.geometry.notna() & ~data.geometry.is_empty].copy()
    data["direct"] = data["werking"].eq("schrijft NoData")
    for index, record in data.iterrows():
        if record["stap"] == "CSV-koppeling":
            value = record["bronwaarde"]
            if pd.isna(value) or not str(value).strip():
                text = "Bronwaarde ontbreekt."
            elif record["reden"] == "Gewascode is geen positief geheel getal.":
                text = "Gewascode is ongeldig."
            else:
                text = f"Geen landgebruikscode voor '{value}'."
        elif record["stap"] == "Actualiteitsfilter":
            text = {
                "Historische registratie: eindRegistratie is gevuld.": "Historische registratie verwijderd.",
                "Beëindigd object: objectEindTijd is gevuld.": "Beëindigd object verwijderd.",
                "Registratie en object beëindigd: beide einddatumvelden zijn gevuld.": "Historisch en beëindigd object verwijderd.",
            }.get(record["reden"], record["reden"])
        elif record["stap"] == "Pandstatus":
            text = f"Pandstatus '{record['bronwaarde']}' uitgesloten."
        else:
            text = record["reden"]
        data.at[index, "reden"] = text
    return data[["geometry", "bron", "reden", "direct"]]


def _unused_terrain(path, bounds, crs) -> gpd.GeoDataFrame:
    """Lees TOP10NL-terrein uitsluitend als aanwijzing voor onverklaarde gaten."""
    layer = "top10nl_terrein_vlak"
    if path is None or layer not in pyogrio.list_layers(path)[:, 0]:
        return _empty_layer(crs)
    data = wgpd.read_file(
        path, layer=layer, bbox=tuple(bounds), columns=["typelandgebruik"]
    )
    if not same_crs(data.crs, crs):
        raise ValueError("TOP10NL-terrein en raster moeten hetzelfde CRS hebben.")
    data = data.dropna(subset=["geometry", "typelandgebruik"]).copy()
    data["reden"] = data["typelandgebruik"].str.strip() + ": terreinlaag niet gebruikt."
    return data


def _unused_bgt(path: Path | None, bounds, crs) -> gpd.GeoDataFrame:
    """Lees actuele vlakken uit aanvullende BGT-lagen die beschikbaar zijn.

    - Een ontbrekende laag is niet gecontroleerd.
    - Punten en lijnen verklaren geen vlakdekking.
    - Alleen de uitleg verandert; er wordt geen landgebruik toegekend.
    """
    if path is None:
        return _empty_layer(crs)
    available = set(pyogrio.list_layers(path)[:, 0])
    parts = []
    for layer in UNUSED_BGT_LAYERS:
        if layer not in available:
            continue
        data = wgpd.read_file(path, layer=layer, bbox=tuple(bounds))
        if not same_crs(data.crs, crs):
            raise ValueError(
                "Aanvullende BGT-laag en raster moeten hetzelfde CRS hebben."
            )
        required = {"bgt-status", "eindRegistratie", "objectEindTijd"}
        if not required.issubset(data.columns):
            raise ValueError(f"Actualiteitsvelden ontbreken in {layer}.")
        current = data.loc[
            data["bgt-status"].eq("bestaand")
            & data["eindRegistratie"].isna()
            & data["objectEindTijd"].isna()
            & data.geom_type.isin(["Polygon", "MultiPolygon"])
        ].copy()
        value = pd.Series("", index=current.index, dtype="string")
        for column in ("bgt-type", "bgt-functie", "bgt-fysiekVoorkomen", "plus-type"):
            if column in current:
                value = value.mask(
                    value.eq(""), current[column].astype("string").fillna("")
                )
        current["bron"] = "BGT"
        current["reden"] = (
            layer
            + ": "
            + value.replace("", "bronwaarde ontbreekt")
            + "; laag niet verwerkt."
        )
        if layer == "bgt_ondersteunendwaterdeel":
            current.loc[value.eq("oever, slootkant"), "reden"] = (
                "Oever/slootkant: geen landgebruikscode."
            )
        parts.append(current[["geometry", "bron", "reden"]])
    if not parts:
        return _empty_layer(crs)
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=crs)


def _nodata_polygons(
    nodata, records, transform, crs, *, terrains=None, unused_bgt=None
) -> gpd.GeoDataFrame:
    """Ken uitleg toe aan lege cellen; bewaar meerdere aanwijzingen samen."""
    labels = np.ones(nodata.shape, dtype="int32")
    combinations = [frozenset(), frozenset()]
    ids = {frozenset(): 1}
    # Direct leeggeschreven BAG-cellen hebben een bekende oorzaak. Andere
    # uitsluitingen op dezelfde plek verklaren die bewuste NoData niet.
    if unused_bgt is None:
        unused_bgt = _empty_layer(crs)
    # Actuele ongebruikte BGT gaat voor historie en TOP10NL-aanwijzingen.
    # Een bewuste BAG-NoData houdt altijd zijn eigen reden.
    steps = (
        (records.loc[~records["direct"]], False, True),
        (unused_bgt, True, False),
        (records.loc[records["direct"]], True, True),
    )
    for selected, replace_previous, all_touched in steps:
        if selected.empty:
            continue
        if replace_previous:
            affected = geometry_mask(
                selected.geometry,
                out_shape=nodata.shape,
                transform=transform,
                all_touched=all_touched,
                invert=True,
            )
            labels[affected & nodata] = 1
        for reason, group in selected.groupby(["bron", "reden"], sort=True):
            affected = (
                geometry_mask(
                    group.geometry,
                    out_shape=nodata.shape,
                    transform=transform,
                    all_touched=all_touched,
                    invert=True,
                )
                & nodata
            )
            # Werk op een kopie zodat nieuw gevormde combinaties niet nogmaals
            # als oude combinatie worden verwerkt binnen dezelfde bronreden.
            previous = labels[affected]
            updated = previous.copy()
            for old_id in np.unique(previous):
                combined = combinations[old_id] | {reason}
                if combined not in ids:
                    ids[combined] = len(combinations)
                    combinations.append(combined)
                updated[previous == old_id] = ids[combined]
            labels[affected] = updated
    # Vul alleen ontbrekende uitleg aan. Bestaande oorzaken blijven behouden.
    if terrains is not None and not terrains.empty:
        for reason, group in terrains.groupby("reden", sort=True):
            affected = (
                geometry_mask(
                    group.geometry,
                    out_shape=nodata.shape,
                    transform=transform,
                    all_touched=False,
                    invert=True,
                )
                & nodata
                & (labels == 1)
            )
            if affected.any():
                labels[affected] = len(combinations)
                combinations.append(frozenset({("TOP10NL", reason)}))
    geometries = []
    sources = []
    reasons = []
    for geometry, label in shapes(labels, mask=nodata, transform=transform):
        combined = sorted(combinations[int(label)])
        if ("BGT", "Oever/slootkant: geen landgebruikscode.") in combined:
            # De oever beschrijft de plek concreter dan het overlappende gebied.
            combined = [
                (source, reason)
                for source, reason in combined
                if not (source == "BGT" and reason.startswith("bgt_functioneelgebied:"))
            ]
        source_names = sorted({source for source, _ in combined})
        sources.append(", ".join(source_names) or "Niet vastgesteld")
        if len(source_names) > 1:
            reasons.append(
                " ".join(f"{source}: {reason}" for source, reason in combined)
            )
        else:
            reasons.append(
                " ".join(reason for _, reason in combined) or NO_SOURCE_REASON
            )
        geometries.append(shape(geometry))
    return gpd.GeoDataFrame(
        {"bron": sources, "reden": reasons}, geometry=geometries, crs=crs
    )


def _raster_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _raster_metadata(path: Path) -> dict:
    stat = path.stat()
    return {_raster_key(path): [stat.st_size, stat.st_mtime_ns]}


def _read_metadata(path: Path) -> dict:
    info = pyogrio.read_info(path, layer=LAYER)
    metadata = info["layer_metadata"] or {}
    if metadata.get("controle_versie") != FORMAT_VERSION:
        raise ValueError(
            f"Verouderd controlebestand: {path}. Maak de NoData-controle opnieuw."
        )
    return json.loads(metadata["rasters"])


def _write_layer(
    data: gpd.GeoDataFrame,
    path: Path,
    *,
    append: bool = False,
    metadata: dict | None = None,
) -> None:
    """Schrijf bron, reden en geometrie; technische gegevens zijn laagmetadata."""
    pyogrio.write_dataframe(
        data[["bron", "reden", "geometry"]],
        path,
        layer=LAYER,
        driver="GPKG",
        geometry_type="Polygon",
        append=append,
        layer_metadata={
            "controle_versie": FORMAT_VERSION,
            "rasters": json.dumps(metadata),
        }
        if metadata is not None
        else None,
    )


def validate_diagnostics(path: Path, raster_path: Path) -> None:
    """Controleer bij hergebruik of de controle bij dit rasterbestand hoort."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Controlebestand ontbreekt: {path}. Bereken de tegel opnieuw met overwrite=True."
        )
    metadata = _read_metadata(path)
    expected = _raster_metadata(raster_path)
    key = _raster_key(raster_path)
    if metadata.get(key) != expected[key]:
        raise ValueError(
            f"Controlebestand hoort niet bij het huidige raster: {path}. "
            "Bereken de tegel opnieuw met overwrite=True."
        )


def merge_diagnostics(
    paths: list[Path], target_path: Path, *, remove_sources: bool = False
) -> Path:
    """Voeg tegelcontroles na afloop samen, zonder gelijktijdige schrijvers.

    Parameters
    ----------
    paths : list[Path]
        Controlebestanden van de geselecteerde tegels; alle moeten bestaan.
    target_path : Path
        Gezamenlijk GeoPackage. Wordt na validatie atomair vervangen.
    remove_sources : bool, optional
        Verwijder de gebruikte tegelcontroles pas nadat het eindbestand is gevalideerd.

    Returns
    -------
    Path
        Eén laag ``nodata`` met ``bron``, ``reden`` en de lege rastercellen als vlakken.
    """
    if not paths:
        raise ValueError("Geen tegelcontroles om samen te voegen.")
    target_path = Path(target_path)
    if target_path.resolve() in {path.resolve() for path in paths}:
        raise ValueError(
            "Uitvoer mag geen invoerbestand vervangen bij het samenvoegen."
        )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".lgb_controle_", dir=target_path.parent
    ) as work:
        temporary = Path(work) / target_path.name
        metadata = {}
        written = False
        crs = None
        for path in paths:
            metadata.update(_read_metadata(path))
            data = wgpd.read_file(path, layer=LAYER)
            if written and not same_crs(crs, data.crs):
                raise ValueError("Tegelcontroles moeten hetzelfde CRS hebben.")
            crs = data.crs
            _write_layer(data, temporary, append=written)
            written = True
        _write_layer(_empty_layer(data.crs), temporary, append=True, metadata=metadata)
        validate_geopackage(temporary)
        temporary.replace(target_path)
    if remove_sources:
        for path in paths:
            path.unlink()
    logger.info("Landelijke controle-uitvoer geschreven: %s", target_path)
    return target_path


def extract_diagnostics(path: Path, target_path: Path, raster_path: Path) -> None:
    """Hergebruik één tegel uit het eindbestand, zonder blijvende losse controles."""
    validate_diagnostics(path, raster_path)
    with rio.open(raster_path) as raster:
        bounds = raster.bounds
    data = wgpd.read_file(path, layer=LAYER, bbox=tuple(bounds))
    data = gpd.clip(data, box(*bounds), keep_geom_type=True)
    data = data.loc[~data.geometry.is_empty & (data.geometry.area > 0)]
    data = data.explode(ignore_index=True)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    _write_layer(data, target_path, metadata=_raster_metadata(raster_path))
