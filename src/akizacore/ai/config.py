from dataclasses import dataclass
from typing import Self

from akizacore.config import Settings


@dataclass(frozen=True)
class AIConfig:
    owner_user_id: int | None = None
    cost_coins: int = 5
    cooldown_s: float = 10.0
    daily_global_limit: int = 100
    daily_user_limit: int = 15
    history_messages: int = 6
    history_max_chars: int = 6000
    memory_limit: int = 5
    memory_max_chars: int = 2000
    max_input_chars: int = 1500
    max_output_tokens: int = 1024
    utc_offset_hours: int = 7
    tools_enabled: bool = True
    max_tool_rounds: int = 3
    retention_days: int = 30

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            owner_user_id=settings.owner_user_id,
            cost_coins=settings.ai_cost_coins,
            cooldown_s=settings.ai_cooldown_s,
            daily_global_limit=settings.ai_daily_global_limit,
            daily_user_limit=settings.ai_daily_user_limit,
            history_messages=settings.ai_history_messages,
            max_input_chars=settings.ai_max_input_chars,
            max_output_tokens=settings.ai_max_output_tokens,
            utc_offset_hours=settings.quota_utc_offset_hours,
            tools_enabled=settings.ai_tools_enabled,
            max_tool_rounds=settings.ai_max_tool_rounds,
            retention_days=settings.ai_retention_days,
        )
