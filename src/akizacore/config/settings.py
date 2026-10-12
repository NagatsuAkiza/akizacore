from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "postgresql+asyncpg://akiza:akiza@localhost:5432/akizacore"

_ENV = SettingsConfigDict(
    env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
)


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

    # Provider AI utama (OpenAI-compatible) dan cadangan
    ai_base_url: str | None = None
    ai_api_key: SecretStr | None = None
    ai_model_fast: str | None = None
    ai_model_smart: str | None = None
    ai_fallback_base_url: str | None = None
    ai_fallback_api_key: SecretStr | None = None
    ai_fallback_model: str | None = None

    # Batas dan biaya AI
    ai_cost_coins: int = 5
    ai_cooldown_s: float = 10.0
    ai_daily_global_limit: int = 500
    ai_daily_user_limit: int = 30
    ai_history_messages: int = 10
    ai_max_input_chars: int = 1500
    ai_max_output_tokens: int = 600
    quota_utc_offset_hours: int = 7  # reset kuota harian tengah malam WIB

    economy_starter_balance: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
