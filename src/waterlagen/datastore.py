from pathlib import Path

from pydantic import ValidationInfo, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from waterlagen.logger import get_logger

logger = get_logger(__name__)

repo_root = Path(__file__).resolve().parents[2]
default_data_path = repo_root / "data"


def _datastore_env_files() -> tuple[Path, ...]:
    """Return datastore config files from lowest to highest precedence."""
    return repo_root / ".datastore", Path.cwd() / ".datastore"


class DataStore(BaseSettings):
    """DataStore to structurally store downloaded and processed data.

    Input arguments `data_dir`, `processed_data_dir` and `processed_data_dir` can be set in an env-file `.datastore`:

    ```
    DATA_DIR=path/to/data/dir
    SOURCE_DATA=path/to/source/data
    PROCESSED_DATA=path/to/processed/data
    ```

    Parameters
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
    model_config = SettingsConfigDict(env_file=None)

    def __init__(self, **values: object) -> None:
        values.setdefault("_env_file", _datastore_env_files())
        super().__init__(**values)

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
        ahn_dir = self.source_data_dir / "ahn"
        ahn_dir.mkdir(exist_ok=True, parents=True)
        return ahn_dir

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


datastore = DataStore()
logger.info(
    "Initialized datastore with source_data_dir=%s and processed_data_dir=%s",
    datastore.source_data_dir,
    datastore.processed_data_dir,
)
