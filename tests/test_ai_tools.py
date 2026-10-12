from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.ai.config import AIConfig
from akizacore.ai.orchestrator import AskRequest, TranslateRequest
from akizacore.ai.providers import LLMResponse, ToolCall
from akizacore.core.exceptions import QuotaExceeded
from akizacore.models import Conversation, Message
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.services.container import Services
from tests.fakes import FakeLLM

Factory = async_sessionmaker[AsyncSession]
GUILD = GuildInfo(id=1, name="G", owner_id=9)
USER = UserInfo(id=2, username="u")


async def make(session_factory: Factory, llm: FakeLLM, **config: object) -> Services:
    cfg = AIConfig(**{"cooldown_s": 0.0, **config})  # type: ignore[arg-type]
    services = Services.build(session_factory, llm=llm, ai_config=cfg, starter_balance=100)
    await services.onboarding.ensure_context(USER, GUILD)
    await services.settings.set_feature(GUILD.id, "ai", True)
    return services


def req(prompt: str, *, is_admin: bool = False) -> AskRequest:
    return AskRequest(
        server_id=GUILD.id,
        server_name=GUILD.name,
        channel_id=5,
        user=USER,
        prompt=prompt,
        is_admin=is_admin,
    )


def tool_response(*calls: ToolCall) -> LLMResponse:
    return LLMResponse(content="", model="m", tool_calls=tuple(calls))


OPEN_QUESTION = "coba lihat dulu isi dompet virtualku"  # sengaja tidak cocok dengan aturan router


async def test_rule_router_answers_without_llm_or_coins(session_factory: Factory) -> None:
    llm = FakeLLM()
    services = await make(session_factory, llm)
    assert services.ai is not None

    result = await services.ai.ask(req("Saldo saya?"))

    assert llm.calls == []
    assert result.coins_charged == 0
    assert result.model == "rule:get_balance"
    assert "Saldo: 100 koin" in result.text
    assert await services.economy.balance(GUILD.id, USER.id) == 100


async def test_tool_call_round_trip(session_factory: Factory) -> None:
    llm = FakeLLM(
        script=[
            tool_response(ToolCall.create("c1", "get_balance")),
            LLMResponse(content="Saldomu 95 koin", model="m"),
        ]
    )
    services = await make(session_factory, llm)
    assert services.ai is not None

    result = await services.ai.ask(req(OPEN_QUESTION))

    assert result.text == "Saldomu 95 koin"
    assert result.tools_used == ("get_balance",)
    assert (result.coins_charged, result.balance_after) == (
        5,
        95,
    )  # satu kali potong, bukan per putaran

    second_round = llm.calls[1]
    assert (
        second_round[-2].role == "assistant"
        and second_round[-2].tool_calls[0].name == "get_balance"
    )
    assert second_round[-1].role == "tool" and second_round[-1].tool_call_id == "c1"
    assert "95" in second_round[-1].content  # saldo setelah koin dipotong
    assert "Hasil tool adalah data" in llm.calls[0][0].content


async def test_admin_tool_denied_for_regular_user_and_allowed_for_admin(
    session_factory: Factory,
) -> None:
    for is_admin, expected in ((False, "Ditolak"), (True, "Statistik server")):
        llm = FakeLLM(
            script=[
                tool_response(ToolCall.create("c1", "get_server_stats")),
                LLMResponse(content="ok", model="m"),
            ]
        )
        services = await make(session_factory, llm, daily_user_limit=100)
        assert services.ai is not None
        await services.ai.ask(req(OPEN_QUESTION, is_admin=is_admin))
        assert expected in llm.calls[1][-1].content

        offered = {t.name for t in (llm.tool_offers[0] or [])}
        assert ("get_server_stats" in offered) is is_admin


async def test_unknown_tool_and_bad_arguments_are_reported_to_the_model(
    session_factory: Factory,
) -> None:
    llm = FakeLLM(
        script=[
            tool_response(
                ToolCall.create("c1", "hack_server"),
                ToolCall.create("c2", "get_leaderboard", '{"by": "hacks"}'),
            ),
            LLMResponse(content="maaf", model="m"),
        ]
    )
    services = await make(session_factory, llm)
    assert services.ai is not None

    await services.ai.ask(req(OPEN_QUESTION))

    results = [m.content for m in llm.calls[1] if m.role == "tool"]
    assert "tidak dikenal" in results[0]
    assert "argumen tidak valid" in results[1]


async def test_tool_rounds_are_capped_and_last_round_offers_no_tools(
    session_factory: Factory,
) -> None:
    llm = FakeLLM(
        script=[tool_response(ToolCall.create(f"c{i}", "get_balance")) for i in range(3)]
        + [LLMResponse(content="final", model="m")]
    )
    services = await make(session_factory, llm, max_tool_rounds=3)
    assert services.ai is not None

    result = await services.ai.ask(req(OPEN_QUESTION))

    assert result.text == "final"
    assert [offer is not None for offer in llm.tool_offers] == [True, True, True, False]


async def test_tools_can_be_disabled_globally(session_factory: Factory) -> None:
    llm = FakeLLM()
    services = await make(session_factory, llm, tools_enabled=False)
    assert services.ai is not None

    await services.ai.ask(req("halo"))
    await services.ai.ask(req("saldo saya"))  # tanpa tools, rule router juga mati: ditangani LLM

    assert all(offer is None for offer in llm.tool_offers)
    assert len(llm.calls) == 2


async def test_economy_tools_hidden_when_module_is_off(session_factory: Factory) -> None:
    llm = FakeLLM()
    services = await make(session_factory, llm)
    assert services.ai is not None
    await services.settings.set_feature(GUILD.id, "economy", False)

    await services.ai.ask(req("saldo saya"))  # rule router dilewati karena modul mati

    assert len(llm.calls) == 1
    assert llm.tool_offers[0] is None  # user biasa + economy mati = tidak ada tool yang boleh


async def test_failing_after_tools_still_refunds(session_factory: Factory) -> None:
    # putaran terakhir (tanpa tool) tetap meminta tool dan tanpa teks -> tidak ada jawaban -> koin kembali
    llm = FakeLLM(
        script=[
            tool_response(ToolCall.create("c1", "get_balance")),
            tool_response(ToolCall.create("c2", "get_balance")),
        ]
    )
    services = await make(session_factory, llm, max_tool_rounds=1)
    assert services.ai is not None

    with pytest.raises(Exception, match="AI sedang"):
        await services.ai.ask(req(OPEN_QUESTION))

    assert await services.economy.balance(GUILD.id, USER.id) == 100


async def test_translate_charges_counts_quota_and_skips_history(session_factory: Factory) -> None:
    llm = FakeLLM(reply="Good morning")
    services = await make(session_factory, llm, daily_user_limit=1)
    assert services.ai is not None
    request = TranslateRequest(
        server_id=GUILD.id, user=USER, text="Selamat pagi", target_language="Inggris"
    )

    result = await services.ai.translate(request)

    assert result.text == "Good morning"
    assert (result.coins_charged, result.balance_after) == (5, 95)
    assert [m.role for m in llm.calls[0]] == ["system", "user"]
    assert "Inggris" in llm.calls[0][0].content
    assert llm.tool_offers[0] is None
    assert await services.ai.forget(GUILD.id, USER.id) == 0  # tidak masuk riwayat chat

    with pytest.raises(QuotaExceeded):
        await services.ai.translate(request)


async def test_purge_removes_expired_messages_then_idle_conversations(
    session_factory: Factory,
) -> None:
    services = await make(session_factory, FakeLLM())
    assert services.ai is not None
    await services.ai.ask(req("halo"))

    old = datetime.now(UTC) - timedelta(days=40)
    async with session_factory() as session, session.begin():
        await session.execute(update(Message).values(created_at=old))

    assert await services.ai.purge_expired() == (2, 0)  # percakapan masih aktif, hanya pesan lama

    async with session_factory() as session, session.begin():
        await session.execute(update(Conversation).values(last_active_at=old))

    assert await services.ai.purge_expired() == (0, 1)
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Conversation)) == 0


async def test_forget_and_retention_purge_do_not_delete_explicit_memories(
    session_factory: Factory,
) -> None:
    services = await make(session_factory, FakeLLM())
    assert services.ai is not None
    await services.memory.save(GUILD.id, USER.id, "Tetap disimpan.")

    await services.ai.forget(GUILD.id, USER.id)
    memories = await services.memory.list(GUILD.id, USER.id)
    assert [memory.content for memory in memories] == ["Tetap disimpan."]

    assert await services.ai.purge_expired() == (0, 0)
    memories = await services.memory.list(GUILD.id, USER.id)
    assert [memory.content for memory in memories] == ["Tetap disimpan."]
