"""Test owner bypass: owner melewati batas operasional, tapi bukan validasi fundamental."""

import random
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import discord
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.ai.config import AIConfig
from akizacore.ai.orchestrator import AskRequest
from akizacore.cogs.settings.setup import _manage_guild_or_owner
from akizacore.core.bot import AkizaBot
from akizacore.core.exceptions import (
    PermissionDenied,
    QuotaExceeded,
    ValidationFailed,
)
from akizacore.models import UserProfile
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.services.container import Services
from akizacore.services.economy_config import EconomyConfig
from akizacore.utils.snowflake import DISCORD_EPOCH_MS
from tests.fakes import FakeLLM

Factory = async_sessionmaker[AsyncSession]
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
GUILD = GuildInfo(id=1, name="G", owner_id=9)


def snowflake_at(moment: datetime) -> int:
    return (int(moment.timestamp() * 1000) - DISCORD_EPOCH_MS) << 22


# Akun owner dan akun biasa sama-sama baru (1 hari) supaya batas umur akun relevan.
OWNER = UserInfo(id=snowflake_at(NOW - timedelta(days=1)), username="owner")
YOUNG = UserInfo(id=snowflake_at(NOW - timedelta(days=1)) + 1, username="young")
# Akun lama (id kecil -> umur sangat tua), dipakai sebagai user biasa yang lolos batas umur.
OLD = UserInfo(id=100, username="old")
OTHER = UserInfo(id=200, username="other")


async def make(
    session_factory: Factory,
    *,
    llm: FakeLLM | None = None,
    economy: dict[str, object] | None = None,
    ai: dict[str, object] | None = None,
    enable_ai: bool = True,
) -> Services:
    eco_values: dict[str, object] = {"starter_balance": 100, "work_min": 20, "work_max": 20}
    eco_values.update(economy or {})
    services = Services.build(
        session_factory,
        llm=llm or FakeLLM(),
        # type: ignore[arg-type]
        ai_config=AIConfig(**{"cooldown_s": 0.0, **(ai or {})}),
        economy_config=EconomyConfig(**eco_values),  # type: ignore[arg-type]
        owner_user_id=OWNER.id,
        clock=lambda: NOW,
        rng=random.Random(1),
    )
    await services.onboarding.ensure_context(OWNER, GUILD)
    for user in (YOUNG, OLD, OTHER):
        await services.onboarding.ensure_user(user)
    if enable_ai:
        await services.settings.set_feature(GUILD.id, "ai", True)
    return services


def ask(user: UserInfo, prompt: str = "halo") -> AskRequest:
    return AskRequest(
        server_id=GUILD.id, server_name=GUILD.name, channel_id=5, user=user, prompt=prompt
    )


# ---------- Economy ----------
async def test_owner_can_claim_daily_repeatedly(session_factory: Factory) -> None:
    s = await make(session_factory)
    await s.economy.daily(GUILD.id, OWNER.id)
    again = await s.economy.daily(GUILD.id, OWNER.id)
    assert again.balance == 100 + 2 * 50

    await s.economy.daily(GUILD.id, OLD.id)
    with pytest.raises(QuotaExceeded):
        await s.economy.daily(GUILD.id, OLD.id)


async def test_owner_has_no_work_cooldown(session_factory: Factory) -> None:
    s = await make(session_factory)
    await s.economy.work(GUILD.id, OWNER.id)
    second = await s.economy.work(GUILD.id, OWNER.id)
    assert second.balance == 100 + 2 * 20

    await s.economy.work(GUILD.id, OLD.id)
    with pytest.raises(QuotaExceeded):
        await s.economy.work(GUILD.id, OLD.id)


async def test_owner_bypasses_transfer_account_age(session_factory: Factory) -> None:
    s = await make(session_factory)
    result = await s.economy.transfer(GUILD.id, OWNER.id, OTHER.id, 10)
    assert result.sender_balance == 90

    with pytest.raises(PermissionDenied):
        await s.economy.transfer(GUILD.id, YOUNG.id, OTHER.id, 10)


async def test_owner_bypasses_transfer_daily_limit(session_factory: Factory) -> None:
    s = await make(session_factory, economy={"starter_balance": 1000, "transfer_daily_limit": 50})
    result = await s.economy.transfer(GUILD.id, OWNER.id, OTHER.id, 200)
    assert result.sender_balance == 800

    with pytest.raises(QuotaExceeded):
        await s.economy.transfer(GUILD.id, OLD.id, OTHER.id, 200)


async def test_owner_transfer_still_validated(session_factory: Factory) -> None:
    s = await make(session_factory)
    with pytest.raises(ValidationFailed):
        # ke diri sendiri
        await s.economy.transfer(GUILD.id, OWNER.id, OWNER.id, 10)
    with pytest.raises(ValidationFailed):
        await s.economy.transfer(GUILD.id, OWNER.id, OTHER.id, 0)
    with pytest.raises(ValidationFailed):
        await s.economy.transfer(GUILD.id, OWNER.id, OTHER.id, -5)


async def test_owner_bypasses_message_xp_cooldown(session_factory: Factory) -> None:
    s = await make(session_factory)
    assert s.economy.message_xp_ready(GUILD.id, OWNER.id)
    assert await s.economy.award_message_xp(GUILD.id, OWNER.id) is not None
    assert s.economy.message_xp_ready(GUILD.id, OWNER.id)
    assert await s.economy.award_message_xp(GUILD.id, OWNER.id) is not None

    assert await s.economy.award_message_xp(GUILD.id, OLD.id) is not None
    assert not s.economy.message_xp_ready(GUILD.id, OLD.id)
    assert await s.economy.award_message_xp(GUILD.id, OLD.id) is None


# ---------- AI ----------
async def test_owner_can_use_ai_when_module_disabled(session_factory: Factory) -> None:
    s = await make(session_factory, enable_ai=False)
    assert s.ai is not None
    assert (await s.ai.ask(ask(OWNER))).text == "jawaban"
    with pytest.raises(PermissionDenied):
        await s.ai.ask(ask(OLD))


async def test_owner_identity_is_sent_to_ai_prompt(session_factory: Factory) -> None:
    llm = FakeLLM()
    s = await make(session_factory, llm=llm)
    assert s.ai is not None

    await s.ai.ask(ask(OWNER, "siapa saya dalam konteks bot ini?"))

    assert "pemilik bot AkizaCore" in llm.calls[-1][0].content


async def test_owner_ignores_ai_opt_out(session_factory: Factory) -> None:
    s = await make(session_factory)
    assert s.ai is not None
    for user in (OWNER, OLD):
        async with session_factory() as session, session.begin():
            profile = await session.get(UserProfile, user.id)
            assert profile is not None
            profile.ai_opt_out = True
    assert (await s.ai.ask(ask(OWNER))).text == "jawaban"
    with pytest.raises(PermissionDenied):
        await s.ai.ask(ask(OLD))


async def test_owner_opt_out_does_not_forward_explicit_memory(
    session_factory: Factory,
) -> None:
    llm = FakeLLM()
    s = await make(session_factory, llm=llm)
    assert s.ai is not None
    await s.memory.save(GUILD.id, OWNER.id, "Rahasia owner")
    async with session_factory() as session, session.begin():
        profile = await session.get(UserProfile, OWNER.id)
        assert profile is not None
        profile.ai_opt_out = True

    await s.ai.ask(ask(OWNER))

    assert "Rahasia owner" not in llm.calls[-1][0].content


async def test_owner_bypasses_ai_cooldown(session_factory: Factory) -> None:
    s = await make(session_factory, ai={"cooldown_s": 60.0})
    assert s.ai is not None
    await s.ai.ask(ask(OWNER))
    await s.ai.ask(ask(OWNER))

    await s.ai.ask(ask(OLD))
    with pytest.raises(QuotaExceeded):
        await s.ai.ask(ask(OLD))


async def test_owner_bypasses_ai_user_quota(session_factory: Factory) -> None:
    s = await make(session_factory, ai={"daily_user_limit": 1})
    assert s.ai is not None
    for _ in range(3):
        await s.ai.ask(ask(OWNER))

    await s.ai.ask(ask(OLD))
    with pytest.raises(QuotaExceeded):
        await s.ai.ask(ask(OLD))


async def test_owner_bypasses_ai_global_quota(session_factory: Factory) -> None:
    s = await make(session_factory, ai={"daily_global_limit": 1})
    assert s.ai is not None
    await s.ai.ask(ask(OLD))  # menghabiskan kuota global
    with pytest.raises(QuotaExceeded):
        await s.ai.ask(ask(OTHER))

    assert (await s.ai.ask(ask(OWNER))).text == "jawaban"


async def test_owner_ai_usage_counts_toward_global_quota(session_factory: Factory) -> None:
    """Owner tidak dibatasi, tapi pemakaiannya tetap tercatat (memakai provider sungguhan)."""
    s = await make(session_factory, ai={"daily_global_limit": 1})
    assert s.ai is not None
    await s.ai.ask(ask(OWNER))
    with pytest.raises(QuotaExceeded):
        await s.ai.ask(ask(OLD))


async def test_owner_is_not_charged_coins(session_factory: Factory) -> None:
    s = await make(session_factory)
    assert s.ai is not None
    result = await s.ai.ask(ask(OWNER))
    assert result.coins_charged == 0
    assert await s.economy.balance(GUILD.id, OWNER.id) == 100

    charged = await s.ai.ask(ask(OLD))
    assert charged.coins_charged == 5
    assert await s.economy.balance(GUILD.id, OLD.id) == 95


async def test_owner_ai_input_still_validated(session_factory: Factory) -> None:
    llm = FakeLLM()
    s = await make(session_factory, llm=llm, ai={"max_input_chars": 10})
    assert s.ai is not None
    with pytest.raises(ValidationFailed):
        await s.ai.ask(ask(OWNER, "x" * 11))
    with pytest.raises(ValidationFailed):
        await s.ai.ask(ask(OWNER, "   "))
    assert llm.calls == []


# ---------- Permission /setup dan helper owner (tanpa database) ----------
def fake_interaction(user_id: int, *, manage_guild: bool | None, owner_id: int) -> MagicMock:
    """manage_guild=None berarti user bukan discord.Member (mis. di DM)."""
    if manage_guild is None:
        user: object = SimpleNamespace(id=user_id)
    else:
        user = MagicMock(spec=discord.Member)
        user.id = user_id
        user.guild_permissions = SimpleNamespace(manage_guild=manage_guild)
    client = SimpleNamespace(is_owner_user=lambda uid: uid == owner_id)
    interaction = MagicMock()
    interaction.user = user
    interaction.client = client
    return interaction


async def test_setup_check_allows_owner_without_manage_guild() -> None:
    assert await _manage_guild_or_owner(fake_interaction(1, manage_guild=False, owner_id=1))


async def test_setup_check_allows_manage_guild_member() -> None:
    assert await _manage_guild_or_owner(fake_interaction(2, manage_guild=True, owner_id=1))


async def test_setup_check_denies_regular_member() -> None:
    assert not await _manage_guild_or_owner(fake_interaction(2, manage_guild=False, owner_id=1))
    assert not await _manage_guild_or_owner(fake_interaction(2, manage_guild=None, owner_id=1))


def test_bot_is_owner_user_matches_configured_owner() -> None:
    stub = SimpleNamespace(settings=SimpleNamespace(owner_user_id=OWNER.id))
    assert AkizaBot.is_owner_user(stub, OWNER.id)  # type: ignore[arg-type]
    assert not AkizaBot.is_owner_user(stub, OLD.id)  # type: ignore[arg-type]
