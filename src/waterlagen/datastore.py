import os
from pathlib import Path

from waterlagen_paths import ahn_tile_directory

from dotenv import dotenv_values

from pydantic import ValidationInfo, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from waterlagen.logger import get_logger

logger = get_logger(__name__)

repo_root = Path(__file__).resolve().parents[2]
default_data_path = repo_root / "data"


def _datastore_env_files() -> tuple[Path, ...]:
    """Return datastore config files from lowest to highest precedence."""
    selected = os.getenv("WATERLAGEN_DATASTORE")
    if selected:
        path = Path(selected).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Datastorebestand ontbreekt: {path}")
        return (path,)
    return repo_root / ".datastore", Path.cwd() / ".datastore"


class DataStore(BaseSettings):
    """DataStore to structurally store downloaded and processed data.

    Configure data directories in ``.datastore``:

    ```
    DATA_DIR=path/to/data/dir
    SOURCE_DATA_DIR=path/to/source/data
    PROCESSED_DATA_DIR=path/to/processed/data
    ```

    Attributes
    ----------
    data_dir : Path
        The root for `source_data_dir` and `processed_data_dir`. Defaults to ./data.
    source_data_dir : Path
        A path for for source data, defaults to `data/source_data`
    processed_data_dir : Path
        A path for for processed data, defaults to `data/processed_data_dir`
    """

    data_dir: Path = default_data_path
    source_data_dir: Path | None = None
    processed_data_dir: Path | None = None
    bag_data_dir: Path | None = None
    bgt_data_dir: Path | None = None
    brp_data_dir: Path | None = None
    top10nl_data_dir: Path | None = None
    cbs_data_dir: Path | None = None
    hydamo_data_dir: Path | None = None
    administratieve_gebieden_data_dir: Path | None = None
    dijkringen_data_dir: Path | None = None
    waterketen_damo_data_dir: Path | None = None
    osm_data_dir: Path | None = None
    liwo_data_dir: Path | None = None
    brandlagen_data_dir: Path | None = None
    ahn_data_dir: Path | None = None
    ahn4_data_dir: Path | None = None
    ahn5_data_dir: Path | None = None
    ahn6_data_dir: Path | None = None
    bag_file: Path | None = None
    bgt_file: Path | None = None
    brp_file: Path | None = None
    top10nl_file: Path | None = None
    ahn_download_dir: Path | None = None
    model_config = SettingsConfigDict(
        env_file=None, env_file_encoding="utf-8-sig", extra="ignore"
    )

    def __init__(self, **values: object) -> None:
        files = values.pop("_env_file", None)
        if files is None:
            files = _datastore_env_files()
        if isinstance(files, (str, Path)):
            files = (files,)
        paths = {}
        for config in files:
            config = Path(config)
            for name, raw in dotenv_values(
                config, encoding="utf-8-sig", interpolate=False
            ).items():
                key = name.lower()
                if key in type(self).model_fields and key != "ahn_download_dir" and raw:
                    paths[key] = Path(os.path.abspath(config.parent / raw))
        # Explicitly selected profiles supply their own paths, also in child processes.
        if not os.getenv("WATERLAGEN_DATASTORE"):
            for key in type(self).model_fields:
                if os.getenv(key.upper()):
                    paths[key] = Path(os.environ[key.upper()])
        if os.getenv("WATERLAGEN_DATASTORE"):
            paths.setdefault("data_dir", Path(files[-1]).parent / "data")
            for key in type(self).model_fields:
                paths.setdefault(key, None)
        values = {**paths, **values, "_env_file": None}
        super().__init__(**values)

    def source_folder(self, source: str) -> Path:
        """Resolve a source directory without creating it."""
        return (
            getattr(self, source + "_data_dir", None) or self.source_data_dir / source
        )

    def ahn_tiles(self, version: int) -> Path:
        """Return the directory containing the GeoTIFFs for one generation."""
        override = getattr(self, f"ahn{version}_data_dir")
        if override is not None:
            return override
        return ahn_tile_directory(self.source_data_dir, version, self.ahn_data_dir)

    def ahn_cache(self) -> Path:
        """Keep publication metadata outside explicitly shared tile sources."""
        if self.ahn_data_dir or any(
            (self.ahn4_data_dir, self.ahn5_data_dir, self.ahn6_data_dir)
        ):
            return self.processed_data_dir / ".waterlagen-cache" / "ahn"
        return self.ahn_dir

    def source_file(self, source: str, filename: str) -> Path:
        """Resolve an explicit file and report a missing shared input."""
        chosen = getattr(self, source + "_file", None)
        if chosen is not None:
            if not chosen.is_file():
                raise FileNotFoundError(
                    f"{source.upper()}-bestand ontbreekt: {chosen}. Kies een ander bestand in de datastore."
                )
            return chosen
        return getattr(self, source + "_dir") / filename

    @property
    def top10nl_path(self) -> Path:
        """Return the configured TOP10NL file or the standard GeoPackage."""
        return self.top10nl_file or self.top10nl_dir / "top10nl_Compleet.gpkg"

    @field_validator("source_data_dir", "processed_data_dir", mode="after")
    def ensure_directory_exists(cls, v: Path | None, info: ValidationInfo) -> Path:
        if v is None:
            data_dir = info.data.get("data_dir") or default_data_path
            if info.field_name == "source_data_dir":
                v = Path(data_dir) / "source_data"
            else:
                v = Path(data_dir) / "processed_data"
        v.mkdir(parents=True, exist_ok=True)
        return v

    @computed_field
    @property
    def ahn_dir(self) -> Path:
        if self.ahn_data_dir:
            return self.ahn_data_dir
        ahn_dir = self.source_folder("ahn")
        ahn_dir.mkdir(exist_ok=True, parents=True)
        return ahn_dir

    @computed_field
    @property
    def bgt_dir(self) -> Path:
        if self.bgt_data_dir:
            return self.bgt_data_dir
        bgt_dir = self.source_folder("bgt")
        bgt_dir.mkdir(exist_ok=True, parents=True)
        return bgt_dir

    @computed_field
    @property
    def bag_dir(self) -> Path:
        if self.bag_data_dir:
            return self.bag_data_dir
        bag_dir = self.source_folder("bag")
        bag_dir.mkdir(exist_ok=True, parents=True)
        return bag_dir

    @computed_field
    @property
    def top10nl_dir(self) -> Path:
        if self.top10nl_data_dir:
            return self.top10nl_data_dir
        top10nl_dir = self.source_folder("top10nl")
        top10nl_dir.mkdir(exist_ok=True, parents=True)
        return top10nl_dir

    @computed_field
    @property
    def brp_dir(self) -> Path:
        if self.brp_data_dir:
            return self.brp_data_dir
        brp_dir = self.source_folder("brp")
        brp_dir.mkdir(exist_ok=True, parents=True)
        return brp_dir

    @computed_field
    @property
    def dijkringen_dir(self) -> Path:
        if self.dijkringen_data_dir:
            return self.dijkringen_data_dir
        dijkringen_dir = self.source_folder("dijkringen")
        dijkringen_dir.mkdir(exist_ok=True, parents=True)
        return dijkringen_dir

    @computed_field
    @property
    def hydamo_dir(self) -> Path:
        if self.hydamo_data_dir:
            return self.hydamo_data_dir
        hydamo_dir = self.source_folder("hydamo")
        hydamo_dir.mkdir(exist_ok=True, parents=True)
        return hydamo_dir

    @computed_field
    @property
    def waterketen_damo_dir(self) -> Path:
        """Return the directory for the PDOK Waterketen DAMO source."""
        if self.waterketen_damo_data_dir:
            return self.waterketen_damo_data_dir
        waterketen_damo_dir = self.source_folder("waterketen_damo")
        waterketen_damo_dir.mkdir(exist_ok=True, parents=True)
        return waterketen_damo_dir

    @computed_field
    @property
    def afwateringseenheden_path(self) -> Path:
        afwateringseenheden_path = self.processed_data_dir / "afwateringseenheden"
        afwateringseenheden_path.mkdir(exist_ok=True, parents=True)
        return afwateringseenheden_path

    @computed_field
    @property
    def administratieve_gebieden_dir(self) -> Path:
        if self.administratieve_gebieden_data_dir:
            return self.administratieve_gebieden_data_dir
        administratieve_gebieden_dir = self.source_folder("administratieve_gebieden")
        administratieve_gebieden_dir.mkdir(exist_ok=True, parents=True)
        return administratieve_gebieden_dir

    @computed_field
    @property
    def cbs_dir(self) -> Path:
        """Return the directory for source data published by CBS."""
        if self.cbs_data_dir:
            return self.cbs_data_dir
        cbs_dir = self.source_folder("cbs")
        cbs_dir.mkdir(exist_ok=True, parents=True)
        return cbs_dir

    @computed_field
    @property
    def vbo_buurt_path(self) -> Path:
        """Return the processed BAG VBO GeoPackage path for compatibility."""
        return self.bag_vbo_path

    @computed_field
    @property
    def vbo_buurt_dir(self) -> Path:
        """Return the directory for shared BAG VBO and CBS-buurt outputs."""
        vbo_buurt_dir = self.processed_data_dir / "vbo_buurt"
        vbo_buurt_dir.mkdir(exist_ok=True, parents=True)
        return vbo_buurt_dir

    @computed_field
    @property
    def bag_vbo_path(self) -> Path:
        """Return the selected BAG VBO GeoPackage path."""
        return self.vbo_buurt_dir / "bag_vbo.gpkg"

    @computed_field
    @property
    def cbs_buurt_path(self) -> Path:
        """Return the CBS buurt polygon GeoPackage path."""
        return self.vbo_buurt_dir / "cbs_buurt.gpkg"

    @computed_field
    @property
    def inwoners_dir(self) -> Path:
        """Return the directory for processed inwoners per woon-VBO data."""
        inwoners_dir = self.processed_data_dir / "inwoners"
        inwoners_dir.mkdir(exist_ok=True, parents=True)
        return inwoners_dir

    @computed_field
    @property
    def inwoners_path(self) -> Path:
        """Return the processed inwoners per woon-VBO GeoPackage path."""
        return self.inwoners_dir / "inwoners.gpkg"

    @computed_field
    @property
    def inwoners_parquet_path(self) -> Path:
        """Return the optional GeoParquet inwoners per woon-VBO output path."""
        return self.inwoners_dir / "inwoners.parquet"

    @computed_field
    @property
    def autos_dir(self) -> Path:
        """Return the directory for processed personenauto's per woon-VBO data."""
        autos_dir = self.processed_data_dir / "autos"
        autos_dir.mkdir(exist_ok=True, parents=True)
        return autos_dir

    @computed_field
    @property
    def autos_path(self) -> Path:
        """Return the processed personenauto's per woon-VBO GeoPackage path."""
        return self.autos_dir / "autos.gpkg"

    @computed_field
    @property
    def autos_parquet_path(self) -> Path:
        """Return the optional GeoParquet personenauto output path."""
        return self.autos_dir / "autos.parquet"


datastore = DataStore()
logger.info(
    "Initialized datastore with source_data_dir=%s and processed_data_dir=%s",
    datastore.source_data_dir,
    datastore.processed_data_dir,
)
