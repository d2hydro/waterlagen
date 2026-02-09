import os
from pathlib import Path

from pydantic import ValidationInfo, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

default_data_path = Path(os.getcwd()) / "data"


class DataStore(BaseSettings):
    data_dir: Path = default_data_path
    source_data_dir: Path | None = None
    processed_data_dir: Path | None = None
    model_config = SettingsConfigDict(env_file=(".datastore"))

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


datastore = DataStore()
