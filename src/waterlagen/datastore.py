from pathlib import Path

from pydantic import Field, ValidationInfo, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from waterlagen.logger import get_logger

logger = get_logger(__name__)


def _find_repo_root() -> Path | None:
    """Recognize a source checkout without mistaking site-packages for one."""
    package_dir = Path(__file__).resolve().parent
    candidate = package_dir.parent.parent
    if package_dir.parent.name == "src" and (candidate / "pyproject.toml").is_file():
        return candidate
    return None


repo_root = _find_repo_root()


def _default_data_path() -> Path:
    """Use repository data for a checkout, or the current work directory."""
    return (repo_root or Path.cwd()) / "data"


default_data_path = _default_data_path()


def _datastore_env_files() -> tuple[Path, ...]:
    """Return datastore config files from lowest to highest precedence."""
    if repo_root is None:
        return (Path.cwd() / ".datastore",)
    return repo_root / ".datastore", Path.cwd() / ".datastore"


class DataStore(BaseSettings):
    """DataStore to structurally store downloaded and processed data.

    The data directories can be configured in an env-file ``.datastore``:

    ```
    DATA_DIR=path/to/data/dir
    SOURCE_DATA_DIR=path/to/source/data
    PROCESSED_DATA_DIR=path/to/processed/data
    ```

    Attributes
    ----------
    data_dir : Path
        Root for source data and processed data. Defaults to ``data`` in the
        source checkout, or in the current working directory for an installed
        package. Explicit values override environment variables and .datastore.
    source_data_dir : Path
        Source directory, defaults to ``data_dir / 'source_data'``.
    processed_data_dir : Path
        Results directory, defaults to ``data_dir / 'processed_data'``.
    """

    data_dir: Path = Field(default_factory=_default_data_path)
    source_data_dir: Path | None = None
    processed_data_dir: Path | None = None
    model_config = SettingsConfigDict(env_file=None, env_file_encoding="utf-8-sig")

    def __init__(self, *, _create_directories: bool = True, **values: object) -> None:
        values.setdefault("_env_file", _datastore_env_files())
        super().__init__(**values)
        if _create_directories:
            self.source_data_dir.mkdir(parents=True, exist_ok=True)
            self.processed_data_dir.mkdir(parents=True, exist_ok=True)

    @field_validator("source_data_dir", "processed_data_dir", mode="after")
    def resolve_directory(cls, v: Path | None, info: ValidationInfo) -> Path:
        if v is None:
            data_dir = info.data.get("data_dir") or _default_data_path()
            if info.field_name == "source_data_dir":
                v = Path(data_dir) / "source_data"
            else:
                v = Path(data_dir) / "processed_data"
        return v

    @computed_field
    @property
    def ahn_dir(self) -> Path:
        ahn_dir = self.source_data_dir / "ahn"
        ahn_dir.mkdir(exist_ok=True, parents=True)
        return ahn_dir

    @computed_field
    @property
    def dgm1_dir(self) -> Path:
        dgm1_dir = self.source_data_dir / "dgm1_nrw"
        dgm1_dir.mkdir(exist_ok=True, parents=True)
        return dgm1_dir

    @computed_field
    @property
    def bgt_dir(self) -> Path:
        bgt_dir = self.source_data_dir / "bgt"
        bgt_dir.mkdir(exist_ok=True, parents=True)
        return bgt_dir

    @computed_field
    @property
    def bag_dir(self) -> Path:
        bag_dir = self.source_data_dir / "bag"
        bag_dir.mkdir(exist_ok=True, parents=True)
        return bag_dir

    @computed_field
    @property
    def top10nl_dir(self) -> Path:
        top10nl_dir = self.source_data_dir / "top10nl"
        top10nl_dir.mkdir(exist_ok=True, parents=True)
        return top10nl_dir

    @computed_field
    @property
    def brp_dir(self) -> Path:
        brp_dir = self.source_data_dir / "brp"
        brp_dir.mkdir(exist_ok=True, parents=True)
        return brp_dir

    @computed_field
    @property
    def dijkringen_dir(self) -> Path:
        dijkringen_dir = self.source_data_dir / "dijkringen"
        dijkringen_dir.mkdir(exist_ok=True, parents=True)
        return dijkringen_dir

    @computed_field
    @property
    def hydamo_dir(self) -> Path:
        hydamo_dir = self.source_data_dir / "hydamo"
        hydamo_dir.mkdir(exist_ok=True, parents=True)
        return hydamo_dir

    @computed_field
    @property
    def afwateringseenheden_path(self) -> Path:
        afwateringseenheden_path = self.processed_data_dir / "afwateringseenheden"
        afwateringseenheden_path.mkdir(exist_ok=True, parents=True)
        return afwateringseenheden_path

    @computed_field
    @property
    def administratieve_gebieden_dir(self) -> Path:
        administratieve_gebieden_dir = self.source_data_dir / "administratieve_gebieden"
        administratieve_gebieden_dir.mkdir(exist_ok=True, parents=True)
        return administratieve_gebieden_dir

    @computed_field
    @property
    def cbs_dir(self) -> Path:
        """Return the directory for source data published by CBS."""
        cbs_dir = self.source_data_dir / "cbs"
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


datastore = DataStore(_create_directories=False)
logger.info(
    "Initialized datastore with source_data_dir=%s and processed_data_dir=%s",
    datastore.source_data_dir,
    datastore.processed_data_dir,
)
