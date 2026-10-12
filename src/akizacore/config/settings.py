from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "postgresql+asyncpg://akiza:akiza@localhost:5432/akizacore"

_ENV = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class DatabaseSettings(BaseSettings):
    """Hanya URL database. Dipakai alembic dan test tanpa perlu token Discord."""

    model_config = _ENV

    database_url: str = DEFAULT_DATABASE_URL


class Settings(BaseSettings):
    """Semua konfigurasi dibaca dari environment / file .env."""

    model_config = _ENV

    environment: Literal["dev", "prod"] = "dev"
    log_level: str = "INFO"

    discord_token: SecretStr
    dev_guild_id: int | None = None

    database_url: str = DEFAULT_DATABASE_URL

    ai_base_url: str | None = None
    ai_api_key: SecretStr | None = None
    ai_model_fast: str | None = None
    ai_model_smart: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
