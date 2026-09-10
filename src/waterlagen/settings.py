from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env"))
    m_to_cm: bool = True
    crs: str = "EPSG:28992"
    afwateringseenheden_workers: int = Field(default=1, ge=1)


settings = Settings()
