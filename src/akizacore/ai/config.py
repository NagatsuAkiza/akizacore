from dataclasses import dataclass
from typing import Self

from akizacore.config import Settings


@dataclass(frozen=True)
class AIConfig:
    cost_coins: int = 5
    cooldown_s: float = 10.0
    daily_global_limit: int = 100
    daily_user_limit: int = 15
    history_messages: int = 6
    history_max_chars: int = 6000
    max_input_chars: int = 1500
    max_output_tokens: int = 1024
    utc_offset_hours: int = 7

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            cost_coins=settings.ai_cost_coins,
            cooldown_s=settings.ai_cooldown_s,
            daily_global_limit=settings.ai_daily_global_limit,
            daily_user_limit=settings.ai_daily_user_limit,
            history_messages=settings.ai_history_messages,
            max_input_chars=settings.ai_max_input_chars,
            max_output_tokens=settings.ai_max_output_tokens,
            utc_offset_hours=settings.quota_utc_offset_hours,
        )
