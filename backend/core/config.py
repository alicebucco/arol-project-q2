"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Secrets are intentionally never hard-coded."""

    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_user: str = "arol"
    postgres_password: SecretStr
    postgres_db: str = "arol"
    postgres_connect_timeout: int = 3
    llm_base_url: str = "https://api.inceptionlabs.ai/v1"
    llm_api_key: SecretStr | None = None
    llm_model: str = "mercury-2"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return one immutable settings instance for the current process."""

    return Settings()
