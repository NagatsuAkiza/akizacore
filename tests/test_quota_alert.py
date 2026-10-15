from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.ai.config import AIConfig
from akizacore.database.repositories import AIUsageRepository
from akizacore.database.session import session_scope
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.services.container import Services
from akizacore.services.quota_alert import QuotaAlerter

TODAY = date(2026, 10, 14)


def test_no_alert_below_threshold() -> None:
    assert QuotaAlerter().next_alert(79, 100, TODAY) is None


def test_alert_at_80_and_100_once_each_per_day() -> None:
    alerter = QuotaAlerter()
    assert alerter.next_alert(80, 100, TODAY) == 80
    assert alerter.next_alert(85, 100, TODAY) is None  # 80% sudah diberitahukan
    assert alerter.next_alert(100, 100, TODAY) == 100
    assert alerter.next_alert(120, 100, TODAY) is None  # 100% sudah diberitahukan
    assert alerter.next_alert(100, 100, TODAY) is None


def test_jump_straight_to_100_skips_the_80_alert() -> None:
    alerter = QuotaAlerter()
    assert alerter.next_alert(100, 100, TODAY) == 100
    assert alerter.next_alert(100, 100, TODAY) is None


def test_alert_resets_on_a_new_day() -> None:
    alerter = QuotaAlerter()
    assert alerter.next_alert(80, 100, TODAY) == 80
    assert alerter.next_alert(80, 100, TODAY + timedelta(days=1)) == 80


def test_zero_limit_never_alerts() -> None:
    assert QuotaAlerter().next_alert(5, 0, TODAY) is None


async def test_global_quota_status_counts_only_successful_llm_calls(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    config = AIConfig(daily_global_limit=10)
    services = Services.build(session_factory, ai_config=config)
    guild = GuildInfo(id=1, name="G", owner_id=9)
    user = UserInfo(id=2, username="alice")
    await services.onboarding.ensure_context(user, guild)
    async with session_scope(session_factory) as session:
        repo = AIUsageRepository(session)
        for status, kind in (("ok", "ask"), ("ok", "translate"), ("error", "ask"), ("ok", "rule")):
            await repo.add(
                server_id=guild.id,
                user_id=user.id,
                model="m",
                prompt_tokens=1,
                completion_tokens=1,
                coins=0,
                kind=kind,
                status=status,
            )

    used, limit, today = await services.usage.global_quota_status()
    assert (used, limit) == (2, 10)
    assert isinstance(today, date)
