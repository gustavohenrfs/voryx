from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VORYX_", env_file=".env", extra="ignore")

    database_url: str
    encryption_key: str
    secret_key: str
    cookie_domain: str = ""
    cookie_secure: bool = True
    cors_origin: str = "https://painel.voryx.pro"
    media_dir: str = "/data/media"
    max_upload_mb: int = 500
    start_background: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
