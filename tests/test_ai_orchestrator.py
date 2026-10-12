import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.ai.config import AIConfig
from akizacore.ai.context import ReplyContext
from akizacore.ai.orchestrator import AskRequest
from akizacore.core.exceptions import (
    InsufficientFunds,
    PermissionDenied,
    ProviderUnavailable,
    QuotaExceeded,
    ValidationFailed,
)
from akizacore.models import AIUsage, Message, UserProfile
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.services.container import Services
from tests.fakes import FakeLLM

Factory = async_sessionmaker[AsyncSession]
GUILD = GuildInfo(id=1, name="G", owner_id=9)
USER = UserInfo(id=2, username="u")


async def make(
    session_factory: Factory,
    llm: FakeLLM | None = None,
    *,
    enable_ai: bool = True,
    starter: int = 100,
    **config: object,
) -> Services:
    cfg = AIConfig(**{"cooldown_s": 0.0, **config})  # type: ignore[arg-type]
    services = Services.build(
        session_factory, llm=llm or FakeLLM(), ai_config=cfg, starter_balance=starter
    )
    await services.onboarding.ensure_context(USER, GUILD)
    if enable_ai:
        await services.settings.set_feature(GUILD.id, "ai", True)
    return services


def req(prompt: str = "halo") -> AskRequest:
    return AskRequest(
        server_id=GUILD.id, server_name=GUILD.name, channel_id=5, user=USER, prompt=prompt
    )


async def test_ask_charges_coins_and_remembers_history(session_factory: Factory) -> None:
    llm = FakeLLM("jawaban")
    services = await make(session_factory, llm)
    assert services.ai is not None

    first = await services.ai.ask(req("halo"))
    assert first.text == "jawaban"
    assert first.balance_after == 95
    assert await services.economy.balance(GUILD.id, USER.id) == 95

    await services.ai.ask(req("lanjut"))
    # system + (user, assistant) dari giliran 1 + user baru
    assert [m.role for m in llm.calls[1]] == ["system", "user", "assistant", "user"]


async def test_reply_context_is_forwarded_and_history_has_author_labels(
    session_factory: Factory,
) -> None:
    llm = FakeLLM("jawaban")
    services = await make(session_factory, llm)
    assert services.ai is not None

    await services.ai.ask(
        AskRequest(
            server_id=GUILD.id,
            server_name=GUILD.name,
            channel_id=5,
            user=USER,
            prompt="itu bukan saya",
            reply_context=ReplyContext(
                author_name="AkizaCore",
                author_id=123,
                content="Itu angka XP lu, kan?",
                is_bot=True,
            ),
        )
    )

    system, prompt = llm.calls[-1][0], llm.calls[-1][-1]
    assert "AkizaCore" in system.content
    assert "Itu angka XP lu" in system.content
    assert prompt.content == "itu bukan saya"

    await services.ai.ask(
        AskRequest(
            server_id=GUILD.id,
            server_name=GUILD.name,
            channel_id=5,
            user=USER,
            prompt="lanjut",
        )
    )
    history = llm.calls[-1][1:-1]
    assert history[0].content.startswith("[u]: ")
    assert history[1].content.startswith("[AkizaCore]: ")


async def test_scoped_memories_are_forwarded_to_ai_context(session_factory: Factory) -> None:
    llm = FakeLLM("jawaban")
    services = await make(session_factory, llm)
    assert services.ai is not None
    await services.memory.save(GUILD.id, USER.id, "Saya suka jawaban singkat.")

    await services.ai.ask(req())

    assert "Saya suka jawaban singkat." in llm.calls[-1][0].content


async def test_ai_must_be_enabled_for_server(session_factory: Factory) -> None:
    services = await make(session_factory, enable_ai=False)
    assert services.ai is not None
    with pytest.raises(PermissionDenied):
        await services.ai.ask(req())


async def test_opt_out_blocks_ai(session_factory: Factory) -> None:
    services = await make(session_factory)
    assert services.ai is not None
    async with session_factory() as session, session.begin():
        profile = await session.get(UserProfile, USER.id)
        assert profile is not None
        profile.ai_opt_out = True
    with pytest.raises(PermissionDenied):
        await services.ai.ask(req())


async def test_provider_failure_refunds_coins(session_factory: Factory) -> None:
    services = await make(session_factory, FakeLLM(fail=True))
    assert services.ai is not None
    with pytest.raises(ProviderUnavailable):
        await services.ai.ask(req())
    assert await services.economy.balance(GUILD.id, USER.id) == 100


async def test_memory_retrieval_failure_refunds_and_does_not_persist(
    session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    services = await make(session_factory)
    assert services.ai is not None

    async def fail_context_for_ai(server_id: int, user_id: int) -> list[object]:
        raise RuntimeError("memory unavailable")

    monkeypatch.setattr(services.memory, "context_for_ai", fail_context_for_ai)

    with pytest.raises(RuntimeError, match="memory unavailable"):
        await services.ai.ask(req())

    assert await services.economy.balance(GUILD.id, USER.id) == 100
    async with session_factory() as session:
        assert await session.scalar(select(func.count(Message.id))) == 0
        assert (
            await session.scalar(
                select(func.count(AIUsage.id)).where(
                    AIUsage.server_id == GUILD.id, AIUsage.user_id == USER.id
                )
            )
            == 0
        )


async def test_insufficient_funds_never_calls_llm(session_factory: Factory) -> None:
    llm = FakeLLM()
    services = await make(session_factory, llm, starter=3)
    assert services.ai is not None
    with pytest.raises(InsufficientFunds):
        await services.ai.ask(req())
    assert llm.calls == []


async def test_user_daily_quota_blocks_without_charging(session_factory: Factory) -> None:
    services = await make(session_factory, daily_user_limit=1)
    assert services.ai is not None
    await services.ai.ask(req())
    with pytest.raises(QuotaExceeded):
        await services.ai.ask(req())
    assert await services.economy.balance(GUILD.id, USER.id) == 95


async def test_global_daily_quota(session_factory: Factory) -> None:
    services = await make(session_factory, daily_global_limit=1)
    assert services.ai is not None
    await services.ai.ask(req())
    with pytest.raises(QuotaExceeded):
        await services.ai.ask(req())


async def test_cooldown_blocks_rapid_requests(session_factory: Factory) -> None:
    services = await make(session_factory, cooldown_s=60.0)
    assert services.ai is not None
    await services.ai.ask(req())
    with pytest.raises(QuotaExceeded):
        await services.ai.ask(req())


async def test_forget_clears_history(session_factory: Factory) -> None:
    llm = FakeLLM()
    services = await make(session_factory, llm)
    assert services.ai is not None
    await services.ai.ask(req())
    assert await services.ai.forget(GUILD.id, USER.id) == 1
    await services.ai.ask(req("mulai lagi"))
    assert [m.role for m in llm.calls[-1]] == ["system", "user"]


async def test_prompt_validation(session_factory: Factory) -> None:
    services = await make(session_factory, max_input_chars=10)
    assert services.ai is not None
    with pytest.raises(ValidationFailed):
        await services.ai.ask(req("   "))
    with pytest.raises(ValidationFailed):
        await services.ai.ask(req("x" * 11))
