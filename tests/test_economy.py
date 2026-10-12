import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.core.exceptions import InsufficientFunds, ValidationFailed
from akizacore.models import Transaction
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.services.container import Services

Factory = async_sessionmaker[AsyncSession]
GUILD = GuildInfo(id=1, name="G", owner_id=9)
USER = UserInfo(id=2, username="u")


async def make(session_factory: Factory, starter: int = 100) -> Services:
    services = Services.build(session_factory, starter_balance=starter)
    await services.onboarding.ensure_context(USER, GUILD)
    return services


async def test_starter_balance_granted_once(session_factory: Factory) -> None:
    services = await make(session_factory)
    assert await services.economy.balance(GUILD.id, USER.id) == 100
    assert await services.economy.balance(GUILD.id, USER.id) == 100


async def test_charge_and_credit_keep_ledger_consistent(session_factory: Factory) -> None:
    services = await make(session_factory)
    await services.economy.charge(GUILD.id, USER.id, 30, kind="test")
    balance = await services.economy.credit(GUILD.id, USER.id, 5, kind="refund")
    assert balance == 75

    async with session_factory() as session:
        total = await session.scalar(select(func.sum(Transaction.amount)))
        last = await session.scalar(
            select(Transaction.balance_after).order_by(Transaction.id.desc()).limit(1)
        )
    assert total == balance == last


async def test_charge_rejects_when_balance_too_low(session_factory: Factory) -> None:
    services = await make(session_factory, starter=10)
    with pytest.raises(InsufficientFunds):
        await services.economy.charge(GUILD.id, USER.id, 11, kind="test")
    assert await services.economy.balance(GUILD.id, USER.id) == 10


async def test_amount_must_be_positive(session_factory: Factory) -> None:
    services = await make(session_factory)
    with pytest.raises(ValidationFailed):
        await services.economy.charge(GUILD.id, USER.id, 0, kind="test")
