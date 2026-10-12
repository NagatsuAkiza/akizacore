import random
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.core.exceptions import (
    InsufficientFunds,
    PermissionDenied,
    QuotaExceeded,
    ValidationFailed,
)
from akizacore.models import EconomyAccount, Transaction
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.services.container import Services
from akizacore.services.economy_config import EconomyConfig
from akizacore.utils.snowflake import DISCORD_EPOCH_MS

Factory = async_sessionmaker[AsyncSession]
GUILD = GuildInfo(id=1, name="G", owner_id=9)
ALICE = UserInfo(id=100, username="alice")
BOB = UserInfo(id=200, username="bob")


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


def snowflake_at(moment: datetime) -> int:
    return (int(moment.timestamp() * 1000) - DISCORD_EPOCH_MS) << 22


async def make(session_factory: Factory, **cfg: object) -> tuple[Services, Clock]:
    clock = Clock()
    values: dict[str, object] = {"starter_balance": 100, "work_min": 20, "work_max": 20}
    values.update(cfg)
    services = Services.build(
        session_factory,
        economy_config=EconomyConfig(**values),  # type: ignore[arg-type]
        clock=clock,
        rng=random.Random(1),
    )
    await services.onboarding.ensure_context(ALICE, GUILD)
    await services.onboarding.ensure_user(BOB)
    return services, clock


async def test_daily_once_per_day(session_factory: Factory) -> None:
    services, clock = await make(session_factory)
    first = await services.economy.daily(GUILD.id, ALICE.id)
    assert (first.amount, first.balance, first.xp_gained) == (50, 150, 20)

    clock.advance(hours=1)
    with pytest.raises(QuotaExceeded):
        await services.economy.daily(GUILD.id, ALICE.id)

    clock.advance(days=1)
    second = await services.economy.daily(GUILD.id, ALICE.id)
    assert second.balance == 200


async def test_work_has_cooldown(session_factory: Factory) -> None:
    services, clock = await make(session_factory)
    first = await services.economy.work(GUILD.id, ALICE.id)
    assert first.amount == 20
    assert first.balance == 120

    with pytest.raises(QuotaExceeded):
        await services.economy.work(GUILD.id, ALICE.id)

    clock.advance(seconds=3601)
    assert (await services.economy.work(GUILD.id, ALICE.id)).balance == 140


async def test_transfer_moves_coins_and_writes_both_ledger_rows(session_factory: Factory) -> None:
    services, _ = await make(session_factory)
    result = await services.economy.transfer(GUILD.id, ALICE.id, BOB.id, 30)
    assert (result.sender_balance, result.receiver_balance) == (70, 130)

    async with session_factory() as session:
        kinds = set(
            await session.scalars(select(Transaction.kind).where(Transaction.amount.in_([-30, 30])))
        )
    assert kinds == {"transfer_out", "transfer_in"}


async def test_transfer_rules(session_factory: Factory) -> None:
    services, clock = await make(session_factory, starter_balance=1000, transfer_daily_limit=100)

    with pytest.raises(ValidationFailed):
        await services.economy.transfer(GUILD.id, ALICE.id, ALICE.id, 10)

    await services.economy.transfer(GUILD.id, ALICE.id, BOB.id, 60)
    with pytest.raises(QuotaExceeded):
        await services.economy.transfer(GUILD.id, ALICE.id, BOB.id, 60)

    clock.advance(days=1)
    await services.economy.transfer(GUILD.id, ALICE.id, BOB.id, 60)


async def test_transfer_insufficient_funds_changes_nothing(session_factory: Factory) -> None:
    services, _ = await make(session_factory, starter_balance=50, transfer_daily_limit=1000)
    with pytest.raises(InsufficientFunds):
        await services.economy.transfer(GUILD.id, ALICE.id, BOB.id, 80)
    assert await services.economy.balance(GUILD.id, ALICE.id) == 50
    assert await services.economy.balance(GUILD.id, BOB.id) == 50


async def test_young_account_cannot_transfer(session_factory: Factory) -> None:
    services, clock = await make(session_factory)
    young = UserInfo(id=snowflake_at(clock.now - timedelta(days=1)), username="baru")
    await services.onboarding.ensure_user(young)
    with pytest.raises(PermissionDenied):
        await services.economy.transfer(GUILD.id, young.id, BOB.id, 10)


async def test_leaderboard_orders_by_balance_and_xp(session_factory: Factory) -> None:
    services, _ = await make(session_factory)
    await services.economy.credit(GUILD.id, ALICE.id, 500, kind="test")
    await services.economy.balance(GUILD.id, BOB.id)

    by_balance = await services.economy.leaderboard(GUILD.id)
    assert [e.username for e in by_balance] == ["alice", "bob"]

    await services.economy.daily(GUILD.id, BOB.id)  # BOB dapat XP, ALICE belum
    by_xp = await services.economy.leaderboard(GUILD.id, by="xp")
    assert by_xp[0].username == "bob"


async def test_message_xp_levels_up_with_bonus_and_respects_cooldown(
    session_factory: Factory,
) -> None:
    services, _ = await make(session_factory, message_xp_min=100, message_xp_max=100)
    result = await services.economy.award_message_xp(GUILD.id, ALICE.id)
    assert result is not None
    assert (result.level, result.leveled_up, result.bonus_coins) == (2, True, 20)
    assert await services.economy.balance(GUILD.id, ALICE.id) == 120

    assert await services.economy.award_message_xp(GUILD.id, ALICE.id) is None


async def test_ledger_always_matches_balance(session_factory: Factory) -> None:
    services, clock = await make(session_factory, starter_balance=500, transfer_daily_limit=1000)
    await services.economy.daily(GUILD.id, ALICE.id)
    await services.economy.work(GUILD.id, ALICE.id)
    await services.economy.transfer(GUILD.id, ALICE.id, BOB.id, 40)
    await services.economy.award_message_xp(GUILD.id, BOB.id)
    clock.advance(days=1)
    await services.economy.daily(GUILD.id, BOB.id)

    async with session_factory() as session:
        sums = dict(
            (
                await session.execute(
                    select(Transaction.user_id, func.sum(Transaction.amount)).group_by(
                        Transaction.user_id
                    )
                )
            ).all()
        )
        balances = dict(
            (await session.execute(select(EconomyAccount.user_id, EconomyAccount.balance))).all()
        )
    assert {k: int(v) for k, v in sums.items()} == balances
