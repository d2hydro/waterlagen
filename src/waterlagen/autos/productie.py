"""Produceer autos met volledige CBS-buurtcontext."""

from pathlib import Path

from waterlagen._cbs_production import produce
from waterlagen._sources import SourcePreparation
from waterlagen.areas import Area, ProductionArea
from waterlagen.datastore import DataStore


def main(
    data_store: DataStore | None = None,
    *,
    area: str | Area | ProductionArea = Area.nederland,
    write_geoparquet: bool = True,
    run_id: str | None = None,
    resume: bool = False,
    overwrite: bool = False,
    refresh_sources: bool = False,
    offline: bool = False,
    preparation: SourcePreparation | None = None,
) -> Path:
    """Produce an area with complete CBS-buurt context.

    Parameters
    ----------
    data_store : DataStore, optional
        Source and production locations.
    area : str or Area or ProductionArea
        Input selection: Nederland, a named polygon or water authority code.
    write_geoparquet : bool
        Write a GeoParquet companion, default True.
    run_id : str, optional
        Unique production run, default a UTC timestamp.
    resume, overwrite : bool
        Reuse or rebuild a compatible existing run.
    refresh_sources : bool
        Refresh sources for a new run; default reuse.
    offline : bool
        Require local source data without network access.
    preparation : SourcePreparation, optional
        Shared source policy for nested productions.

    Returns
    -------
    pathlib.Path
        Produced GeoPackage; complete selected buurten are retained.
    """
    return produce(
        "autos",
        data_store,
        area=area,
        write_geoparquet=write_geoparquet,
        run_id=run_id,
        resume=resume,
        overwrite=overwrite,
        refresh_sources=refresh_sources,
        offline=offline,
        preparation=preparation,
    )
