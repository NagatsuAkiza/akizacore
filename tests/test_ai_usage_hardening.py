from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.ai.config import AIConfig
from akizacore.ai.orchestrator import AskRequest
from akizacore.core.exceptions import QuotaExceeded
from akizacore.database.repositories import AIUsageRepository
from akizacore.database.session import session_scope
from akizacore.models import AIUsage
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.services.ai_usage import AIUsageService
from akizacore.services.container import Services
from tests.fakes import FakeLLM

Factory = async_sessionmaker[AsyncSession]
GUILD = GuildInfo(id=1, name="G", owner_id=9)
USER = UserInfo(id=2, username="alice")
USER2 = UserInfo(id=3, username="bob")


async def make(session_factory: Factory, llm: FakeLLM | None = None, **cfg: object) -> Services:
    config = AIConfig(**{"cooldown_s": 0.0, "daily_user_limit": 5, "daily_global_limit": 50, **cfg})  # type: ignore[arg-type]
    services = Services.build(session_factory, llm=llm, ai_config=config, starter_balance=100)
    await services.onboarding.ensure_context(USER, GUILD)
    await services.onboarding.ensure_context(USER2, GUILD)
    await services.settings.set_feature(GUILD.id, "ai", True)
    return services


async def add_row(session_factory: Factory, *, user_id: int = USER.id) -> None:
    async with session_scope(session_factory) as session:
        await AIUsageRepository(session).add(
            server_id=GUILD.id,
            user_id=user_id,
            model="m1",
            prompt_tokens=10,
            completion_tokens=5,
            coins=5,
            latency_ms=100,
        )


async def age_oldest_row(session_factory: Factory, days: int) -> None:
    async with session_scope(session_factory) as session:
        oldest = (await session.execute(select(func.min(AIUsage.id)))).scalar_one()
        await session.execute(
            update(AIUsage)
            .where(AIUsage.id == oldest)
            .values(created_at=datetime.now(UTC) - timedelta(days=days))
        )


async def count_rows(session_factory: Factory) -> int:
    async with session_factory() as session:
        return (await session.execute(select(func.count(AIUsage.id)))).scalar_one()


def ask_req(user: UserInfo = USER, prompt: str = "halo") -> AskRequest:
    return AskRequest(
        server_id=GUILD.id, server_name=GUILD.name, channel_id=5, user=user, prompt=prompt
    )


# ---------- Retensi ----------


async def test_purge_expired_deletes_only_rows_past_retention(session_factory: Factory) -> None:
    services = await make(session_factory)
    await add_row(session_factory)
    await add_row(session_factory)
    await age_oldest_row(session_factory, days=120)

    assert await services.usage.purge_expired() == 1
    assert await count_rows(session_factory) == 1
    assert await services.usage.purge_expired() == 0


async def test_purge_never_goes_below_minimum_retention(session_factory: Factory) -> None:
    await make(session_factory)
    service = AIUsageService(
        session_factory,
        daily_user_limit=5,
        daily_global_limit=50,
        utc_offset_hours=7,
        retention_days=1,  # diminta 1 hari, tapi minimal 7 hari
    )
    await add_row(session_factory)
    await add_row(session_factory)
    await age_oldest_row(session_factory, days=3)

    assert await service.purge_expired() == 0
    await age_oldest_row(session_factory, days=8)
    assert await service.purge_expired() == 1


# ---------- Penolakan kuota ----------


async def test_user_quota_rejection_is_recorded_but_not_counted(session_factory: Factory) -> None:
    services = await make(session_factory, FakeLLM(), daily_user_limit=1)
    assert services.ai is not None
    await services.ai.ask(ask_req())
    with pytest.raises(QuotaExceeded):
        await services.ai.ask(ask_req())

    report = await services.usage.server_report(GUILD.id)
    assert (report.totals.requests, report.totals.rejected, report.totals.errors) == (1, 1, 0)
    assert (await services.usage.my_usage(USER.id)).used_today == 1  # kuota tidak bertambah
    async with session_factory() as session:
        row = (
            await session.execute(select(AIUsage).where(AIUsage.status == "rejected"))
        ).scalar_one()
    assert (row.error_code, row.kind, row.user_id) == ("user_quota", "ask", USER.id)


async def test_global_quota_rejection_is_recorded(session_factory: Factory) -> None:
    services = await make(session_factory, FakeLLM(), daily_global_limit=1)
    assert services.ai is not None
    await services.ai.ask(ask_req(USER))
    with pytest.raises(QuotaExceeded, match="Kuota AI harian bot"):
        await services.ai.ask(ask_req(USER2))

    report = await services.usage.server_report(GUILD.id)
    assert report.totals.rejected == 1
    async with session_factory() as session:
        row = (
            await session.execute(select(AIUsage).where(AIUsage.status == "rejected"))
        ).scalar_one()
    assert (row.error_code, row.user_id) == ("global_quota", USER2.id)


async def test_cooldown_rejection_is_not_recorded(session_factory: Factory) -> None:
    services = await make(session_factory, FakeLLM(), cooldown_s=60.0)
    assert services.ai is not None
    await services.ai.ask(ask_req())
    with pytest.raises(QuotaExceeded, match="Tunggu"):
        await services.ai.ask(ask_req())

    report = await services.usage.server_report(GUILD.id)
    assert report.totals.rejected == 0
