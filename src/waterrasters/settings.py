from pathlib import Path

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

repos_root = Path(__file__).parents[2]
default_data_path = repos_root / "data"


class Settings(BaseSettings):
    source_data_dir: Path = default_data_path / "source_data"
    processed_data_dir: Path = default_data_path / "processed_data"
    model_config = SettingsConfigDict(env_file=(".env"))
    m_to_cm: bool = True

    @field_validator("source_data_dir", "processed_data_dir", mode="after")
    def ensure_directory_exists(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    @computed_field
    @property
    def ahn_dir(self) -> Path:
        ahn_dir = self.source_data_dir / "ahn"
        ahn_dir.mkdir(exist_ok=True, parents=True)
        return ahn_dir


settings = Settings()
