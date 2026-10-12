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
    ai_extra_body: str | None = None  # JSON, mis. {"reasoning_effort":"low"}
    ai_fallback_base_url: str | None = None
    ai_fallback_api_key: SecretStr | None = None
    ai_fallback_model: str | None = None
    ai_fallback_extra_body: str | None = None

    # Batas dan biaya AI
    ai_cost_coins: int = 5
    ai_cooldown_s: float = 10.0
    ai_daily_global_limit: int = 100
    ai_daily_user_limit: int = 15
    ai_history_messages: int = 6
    ai_max_input_chars: int = 1500
    ai_max_output_tokens: int = 1024
    quota_utc_offset_hours: int = 7  # reset kuota harian tengah malam WIB

    economy_starter_balance: int = 100
    economy_daily_amount: int = 50
    economy_daily_xp: int = 20
    economy_work_min: int = 15
    economy_work_max: int = 45
    economy_work_cooldown_s: int = 3600
    economy_work_xp: int = 10
    economy_transfer_daily_limit: int = 500
    economy_transfer_min_account_age_days: int = 7
    economy_message_xp_min: int = 5
    economy_message_xp_max: int = 15
    economy_message_xp_cooldown_s: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
