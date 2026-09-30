"""Maak losse, geïndexeerde GeoPackages met actuele BGT-vlakken."""

import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

from osgeo import gdal, ogr

from waterlagen._downloads import validate_geopackage
from waterlagen.bgt.download import (
    _gml_surface_source,
    _replace_with_retry,
    _vsizip_gml_path,
)
from waterlagen.logger import get_logger

logger = get_logger(__name__)

SURFACE_LAYERS = (
    "waterdeel",
    "ondersteunendwaterdeel",
    "wegdeel",
    "ondersteunendwegdeel",
    "begroeidterreindeel",
    "onbegroeidterreindeel",
    "overbruggingsdeel",
    "tunneldeel",
    "kunstwerkdeel",
    "overigbouwwerk",
    "scheiding",
    "overigescheiding",
    "gebouwinstallatie",
    "vegetatieobject",
    "ongeclassificeerdobject",
    "pand",
    "functioneelgebied",
)


def combine_surface_layers(paths: list[Path], target: Path) -> Path:
    """Voeg voorbereide vlaklagen samen met een ruimtelijke index per laag.

    Parameters
    ----------
    paths : list[Path]
        Gevalideerde GeoPackages, elk met één BGT-vlaklaag.
    target : Path
        Gezamenlijk GeoPackage. Een bestaand bestand wordt pas vervangen
        nadat alle lagen en objectaantallen zijn gecontroleerd.

    Returns
    -------
    Path
        Het afgeronde GeoPackage. Bronbestanden blijven behouden voor hervatten.
    """
    if not paths:
        raise ValueError("Geen actuele vlaklagen om samen te voegen")
    if len({path.stem for path in paths}) != len(paths):
        raise ValueError("Dubbele laagnamen bij samenvoegen")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".bgt_samenvoegen_", dir=target.parent
    ) as work:
        temporary = Path(work) / target.name
        for path in paths:
            layer = path.stem
            count = validate_surface_file(path, layer)
            logger.info("Laag toevoegen aan gezamenlijk GeoPackage: %s", layer)
            with (
                gdal.ExceptionMgr(useExceptions=True),
                gdal.VectorTranslate(
                    str(temporary),
                    str(path),
                    format="GPKG",
                    accessMode="update" if temporary.exists() else None,
                    layers=[layer],
                    layerName=layer,
                    layerCreationOptions=["SPATIAL_INDEX=YES", "GEOMETRY_NAME=geom"],
                    transactionSize=100_000,
                ) as result,
            ):
                result.GetLayerByName(layer).GetFeatureCount()
                result.GetLayerByName(layer).GetExtent()
            if validate_surface_file(temporary, layer) != count:
                raise ValueError(f"Objectaantal verschilt na samenvoegen: {layer}")
        _replace_with_retry(temporary, target)
    return target


def validate_surface_file(path: Path, layer: str) -> int:
    """Controleer index, geometriesoort en opgeslagen metadata zonder vlakscan.

    Parameters
    ----------
    path : Path
        GeoPackage met één laag.
    layer : str
        Naam van de verwachte laag.

    Returns
    -------
    int
        Opgeslagen objectaantal.
    """
    validate_geopackage(path)
    with closing(
        sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        geometry = connection.execute(
            "SELECT column_name, geometry_type_name, srs_id FROM gpkg_geometry_columns WHERE table_name=?",
            (layer,),
        ).fetchone()
        if geometry != ("geom", "MULTIPOLYGON", 28992):
            raise ValueError(f"Onverwachte geometrie of CRS in {path}: {geometry}")
        index = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (f"rtree_{layer}_geom",),
        ).fetchone()
        count = connection.execute(
            "SELECT feature_count FROM gpkg_ogr_contents WHERE table_name=?", (layer,)
        ).fetchone()
        extent = connection.execute(
            "SELECT min_x,min_y,max_x,max_y FROM gpkg_contents WHERE table_name=?",
            (layer,),
        ).fetchone()
        if index is None or count is None or count[0] is None:
            raise ValueError(f"Ruimtelijke index of objectaantal ontbreekt in {path}")
        if count[0] and (extent is None or any(value is None for value in extent)):
            raise ValueError(f"Laagbegrenzing ontbreekt in {path}")
        return int(count[0])


def prepare_surface_layer(
    archive: Path, output_dir: Path, feature_type: str, *, overwrite: bool = False
) -> Path | None:
    """Schrijf actuele vlakken uit één GML-laag naar een geïndexeerd GeoPackage.

    Parameters
    ----------
    archive : Path
        Bestaande landelijke GML Light-ZIP; wordt niet gewijzigd.
    output_dir : Path
        Map voor afzonderlijke GeoPackages en tijdelijke conversiebestanden.
    feature_type : str
        BGT-objecttype zonder het voorvoegsel ``bgt_``.
    overwrite : bool, default False
        Hergebruik een bestaand, gecontroleerd bestand tenzij True.

    Returns
    -------
    Path or None
        Afgerond GeoPackage, of None als de laag geen actuele vlakken bevat.
        De tijdelijke uitvoer vervangt het doel pas na validatie.
    """
    if feature_type not in SURFACE_LAYERS:
        raise ValueError(f"Geen geselecteerde BGT-vlaklaag: {feature_type}")
    layer = f"bgt_{feature_type}"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{layer}.gpkg"
    if target.exists() and not overwrite:
        validate_surface_file(target, layer)
        logger.info("Hergebruik %s", target)
        return target
    with zipfile.ZipFile(archive) as source_zip:
        members = [
            name for name in source_zip.namelist() if Path(name).name == f"{layer}.gml"
        ]
    if len(members) != 1:
        raise ValueError(f"Verwacht één {layer}.gml in {archive}")
    source_path = _vsizip_gml_path(archive, members[0])
    logger.info("Actuele vlakken voorbereiden: %s", layer)
    with tempfile.TemporaryDirectory(prefix=f".{layer}_", dir=output_dir) as work:
        temporary = Path(work) / target.name
        with (
            gdal.ExceptionMgr(useExceptions=True),
            _gml_surface_source(source_path, layer_name=layer, work_dir=Path(work)) as (
                gml,
                options,
            ),
            gdal.OpenEx(gml, gdal.OF_VECTOR, open_options=options) as source,
        ):
            definition = source.GetLayer(0).GetLayerDefn()
            fields = {
                definition.GetFieldDefn(i).GetName()
                for i in range(definition.GetFieldCount())
            }
            if "bgt-status" not in fields:
                if source.GetLayer(0).GetFeatureCount() == 0:
                    return None
                raise ValueError(f"bgt-status ontbreekt in {layer}")
            filters = [
                "\"bgt-status\" = 'bestaand'",
                "OGR_GEOMETRY IN ('POLYGON','MULTIPOLYGON','CURVEPOLYGON','MULTISURFACE')",
            ]
            # Als een veld in de hele GML ontbreekt, hebben alle objecten daar NULL.
            for field in ("eindRegistratie", "objectEindTijd"):
                if field in fields:
                    filters.append(f'"{field}" IS NULL')
            with gdal.VectorTranslate(
                str(temporary),
                source,
                format="GPKG",
                layerName=layer,
                where=" AND ".join(filters),
                geometryType="MULTIPOLYGON",
                srcSRS="EPSG:28992",
                dstSRS="EPSG:28992",
                datasetCreationOptions=["ADD_GPKG_OGR_CONTENTS=YES"],
                layerCreationOptions=[
                    "SPATIAL_INDEX=YES",
                    "GEOMETRY_NAME=geom",
                    "PRECISION=NO",
                ],
                transactionSize=100_000,
            ) as result:
                for field in ("eindRegistratie", "objectEindTijd"):
                    if field not in fields:
                        result.GetLayer(0).CreateField(
                            ogr.FieldDefn(field, ogr.OFTDateTime)
                        )
                count = result.GetLayer(0).GetFeatureCount()
                if count:
                    result.GetLayer(0).GetExtent()
        if not count:
            logger.info("Geen actuele vlakken in %s", layer)
            return None
        validate_surface_file(temporary, layer)
        _replace_with_retry(temporary, target)
    logger.info("Gereed: %s (%s vlakken)", target, count)
    return target
