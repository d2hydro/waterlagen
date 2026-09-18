from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig")
    m_to_cm: bool = True
    crs: str = "EPSG:28992"
    afwateringseenheden_workers: int = 4


settings = Settings()
