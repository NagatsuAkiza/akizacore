from dataclasses import dataclass
from typing import Self

from akizacore.config import Settings


@dataclass(frozen=True)
class EconomyConfig:
    owner_user_id: int | None = None
    starter_balance: int = 100
    daily_amount: int = 50
    daily_xp: int = 20
    work_min: int = 15
    work_max: int = 45
    work_cooldown_s: int = 3600
    work_xp: int = 10
    transfer_daily_limit: int = 500
    transfer_min_account_age_days: int = 7
    message_xp_min: int = 5
    message_xp_max: int = 15
    message_xp_cooldown_s: float = 60.0
    utc_offset_hours: int = 7

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            owner_user_id=settings.owner_user_id,
            starter_balance=settings.economy_starter_balance,
            daily_amount=settings.economy_daily_amount,
            daily_xp=settings.economy_daily_xp,
            work_min=settings.economy_work_min,
            work_max=settings.economy_work_max,
            work_cooldown_s=settings.economy_work_cooldown_s,
            work_xp=settings.economy_work_xp,
            transfer_daily_limit=settings.economy_transfer_daily_limit,
            transfer_min_account_age_days=settings.economy_transfer_min_account_age_days,
            message_xp_min=settings.economy_message_xp_min,
            message_xp_max=settings.economy_message_xp_max,
            message_xp_cooldown_s=settings.economy_message_xp_cooldown_s,
            utc_offset_hours=settings.quota_utc_offset_hours,
        )
