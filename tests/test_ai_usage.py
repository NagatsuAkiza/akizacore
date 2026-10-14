import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.ai.config import AIConfig
from akizacore.ai.orchestrator import AskRequest, TranslateRequest
from akizacore.core.exceptions import ProviderUnavailable
from akizacore.database.repositories import AIUsageRepository
from akizacore.database.session import session_scope
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.services.container import Services
from tests.fakes import FakeLLM

Factory = async_sessionmaker[AsyncSession]
GUILD = GuildInfo(id=1, name="G", owner_id=9)
GUILD2 = GuildInfo(id=2, name="H", owner_id=9)
USER = UserInfo(id=2, username="alice")
USER2 = UserInfo(id=3, username="bob")


async def make(session_factory: Factory, llm: FakeLLM | None = None) -> Services:
    cfg = AIConfig(cooldown_s=0.0, daily_user_limit=5, daily_global_limit=50)
    services = Services.build(session_factory, llm=llm, ai_config=cfg, starter_balance=100)
    await services.onboarding.ensure_context(USER, GUILD)
    await services.onboarding.ensure_context(USER2, GUILD)
    await services.onboarding.ensure_context(USER, GUILD2)
    await services.settings.set_feature(GUILD.id, "ai", True)
    return services


async def add(
    session_factory: Factory,
    *,
    server_id: int = GUILD.id,
    user_id: int = USER.id,
    model: str = "m1",
    kind: str = "ask",
    status: str = "ok",
    prompt: int = 10,
    completion: int = 5,
    coins: int = 5,
    latency: int | None = 100,
    tools: tuple[str, ...] = (),
    error_code: str | None = None,
) -> None:
    async with session_scope(session_factory) as session:
        await AIUsageRepository(session).add(
            server_id=server_id,
            user_id=user_id,
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            coins=coins,
            kind=kind,
            status=status,
            latency_ms=latency,
            tools=tools,
            error_code=error_code,
        )


def ask_req(prompt: str = "halo") -> AskRequest:
    return AskRequest(
        server_id=GUILD.id, server_name=GUILD.name, channel_id=5, user=USER, prompt=prompt
    )


# ---------- Repository dan service ----------


async def test_quota_counts_ignore_errors_and_rule_hits(session_factory: Factory) -> None:
    services = await make(session_factory)
    await add(session_factory)
    await add(session_factory, status="error", model="-", prompt=0, completion=0, coins=0)
    await add(session_factory, kind="rule", model="rule:get_balance", prompt=0, completion=0)

    mine = await services.usage.my_usage(USER.id)
    assert mine.used_today == 1
    assert mine.global_used_today == 1


async def test_server_report_totals_and_breakdowns(session_factory: Factory) -> None:
    services = await make(session_factory)
    await add(session_factory, latency=100, tools=("get_balance",))
    await add(session_factory, model="m2", kind="translate", latency=300, prompt=20, completion=10)
    await add(session_factory, user_id=USER2.id, latency=200, tools=("get_balance", "get_stats"))
    await add(
        session_factory,
        kind="rule",
        model="rule:get_balance",
        prompt=0,
        completion=0,
        coins=0,
        latency=5,
        tools=("get_balance",),
    )
    await add(
        session_factory,
        status="error",
        model="-",
        prompt=0,
        completion=0,
        coins=0,
        latency=50,
        error_code="ProviderUnavailable",
    )
    await add(session_factory, server_id=GUILD2.id)  # server lain: tidak boleh ikut

    report = await services.usage.server_report(GUILD.id, days=7)
    totals = report.totals
    assert (totals.requests, totals.rule_hits, totals.errors) == (3, 1, 1)
    assert (totals.prompt_tokens, totals.completion_tokens, totals.coins) == (40, 20, 15)
    assert totals.avg_latency_ms == 200
    assert totals.p95_latency_ms is not None and 200 <= totals.p95_latency_ms <= 300

    assert len(report.daily) == 7
    assert sum(d.requests for d in report.daily) == 3
    assert report.daily[-1].requests == 3  # semua baris dibuat hari ini
    assert report.daily[-1].tokens == 60

    assert [u.user_id for u in report.top_users] == [str(USER.id), str(USER2.id)]
    assert report.top_users[0].username == "alice"
    assert report.top_users[0].requests == 2

    assert {m.name for m in report.by_model} == {"m1", "m2"}
    assert {k.name: k.requests for k in report.by_kind} == {"ask": 2, "translate": 1, "rule": 1}
    assert {t.name: t.requests for t in report.tools} == {"get_balance": 3, "get_stats": 1}
    assert [e.error_code for e in report.recent_errors] == ["ProviderUnavailable"]
    assert report.recent_errors[0].kind == "ask"


async def test_server_report_days_is_clamped_and_empty_server_is_zero(
    session_factory: Factory,
) -> None:
    services = await make(session_factory)
    report = await services.usage.server_report(GUILD2.id, days=1000)
    assert report.days == 90
    assert len(report.daily) == 90
    assert report.totals.requests == 0
    assert report.totals.avg_latency_ms is None
    assert report.top_users == []


async def test_my_usage_reports_quota_and_week(session_factory: Factory) -> None:
    services = await make(session_factory)
    await add(session_factory)
    await add(session_factory, status="error", model="-", prompt=0, completion=0, coins=0)
    await add(session_factory, user_id=USER2.id)

    mine = await services.usage.my_usage(USER.id)
    assert (mine.used_today, mine.user_limit) == (1, 5)
    assert (mine.global_used_today, mine.global_limit) == (2, 50)
    assert mine.tokens_today == 15
    assert mine.coins_today == 5
    assert mine.last_7_days.requests == 1
    assert mine.last_7_days.errors == 1


# ---------- Pencatatan oleh orchestrator ----------


async def test_ask_records_kind_latency_and_quota(session_factory: Factory) -> None:
    services = await make(session_factory, FakeLLM())
    assert services.ai is not None
    await services.ai.ask(ask_req("halo"))

    report = await services.usage.server_report(GUILD.id)
    assert report.totals.requests == 1
    assert report.totals.avg_latency_ms is not None
    assert [k.name for k in report.by_kind] == ["ask"]
    assert report.by_model[0].name == "fake-model"
    assert (await services.usage.my_usage(USER.id)).used_today == 1


async def test_translate_is_tracked_as_translate(session_factory: Factory) -> None:
    services = await make(session_factory, FakeLLM())
    assert services.ai is not None
    await services.ai.translate(
        TranslateRequest(server_id=GUILD.id, user=USER, text="halo", target_language="inggris")
    )
    report = await services.usage.server_report(GUILD.id)
    assert [k.name for k in report.by_kind] == ["translate"]


async def test_provider_failure_is_tracked_but_not_counted_in_quota(
    session_factory: Factory,
) -> None:
    services = await make(session_factory, FakeLLM(fail=True))
    assert services.ai is not None
    with pytest.raises(ProviderUnavailable):
        await services.ai.ask(ask_req())

    report = await services.usage.server_report(GUILD.id)
    assert (report.totals.requests, report.totals.errors) == (0, 1)
    assert report.recent_errors[0].error_code == "ProviderUnavailable"
    assert report.recent_errors[0].kind == "ask"
    assert (await services.usage.my_usage(USER.id)).used_today == 0
    assert await services.economy.balance(GUILD.id, USER.id) == 100  # koin tetap di-refund


async def test_rule_hit_is_tracked_without_consuming_quota(session_factory: Factory) -> None:
    services = await make(session_factory, FakeLLM())
    assert services.ai is not None
    result = await services.ai.ask(ask_req("saldo saya"))
    assert result.model == "rule:get_balance"

    report = await services.usage.server_report(GUILD.id)
    assert (report.totals.requests, report.totals.rule_hits) == (0, 1)
    assert {t.name: t.requests for t in report.tools} == {"get_balance": 1}
    assert (await services.usage.my_usage(USER.id)).used_today == 0
