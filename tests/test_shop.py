import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.core.exceptions import InsufficientFunds, NotFound, ValidationFailed
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.services.container import Services

Factory = async_sessionmaker[AsyncSession]
GUILD = GuildInfo(id=1, name="G", owner_id=9)
USER = UserInfo(id=2, username="u")


async def make(session_factory: Factory, starter: int = 100) -> Services:
    services = Services.build(session_factory, starter_balance=starter)
    await services.onboarding.ensure_context(USER, GUILD)
    return services


async def test_buy_updates_balance_stock_and_inventory(session_factory: Factory) -> None:
    s = await make(session_factory)
    await s.shop.add_item(GUILD.id, "Pedang", 40, stock=2)

    result = await s.shop.buy(GUILD.id, USER.id, "pedang")  # nama tidak peka huruf besar/kecil
    assert (result.total_cost, result.balance) == (40, 60)

    assert (await s.shop.list_items(GUILD.id))[0].stock == 1
    inventory = await s.shop.inventory(GUILD.id, USER.id)
    assert [(i.name, i.quantity) for i in inventory] == [("Pedang", 1)]

    await s.shop.buy(GUILD.id, USER.id, "Pedang")
    assert (await s.shop.inventory(GUILD.id, USER.id))[0].quantity == 2


async def test_out_of_stock(session_factory: Factory) -> None:
    s = await make(session_factory)
    await s.shop.add_item(GUILD.id, "Langka", 10, stock=1)
    await s.shop.buy(GUILD.id, USER.id, "Langka")
    with pytest.raises(ValidationFailed):
        await s.shop.buy(GUILD.id, USER.id, "Langka")


async def test_insufficient_funds_leaves_stock_and_inventory_untouched(
    session_factory: Factory,
) -> None:
    s = await make(session_factory, starter=10)
    await s.shop.add_item(GUILD.id, "Mahal", 40, stock=5)
    with pytest.raises(InsufficientFunds):
        await s.shop.buy(GUILD.id, USER.id, "Mahal")
    assert (await s.shop.list_items(GUILD.id))[0].stock == 5
    assert await s.shop.inventory(GUILD.id, USER.id) == []
    assert await s.economy.balance(GUILD.id, USER.id) == 10


async def test_remove_hides_item_and_readd_reactivates(session_factory: Factory) -> None:
    s = await make(session_factory)
    first = await s.shop.add_item(GUILD.id, "Topi", 20)
    await s.shop.remove_item(GUILD.id, "Topi")

    assert await s.shop.list_items(GUILD.id) == []
    with pytest.raises(NotFound):
        await s.shop.buy(GUILD.id, USER.id, "Topi")

    again = await s.shop.add_item(GUILD.id, "Topi", 50)
    assert again.id == first.id
    assert [(i.name, i.price) for i in await s.shop.list_items(GUILD.id)] == [("Topi", 50)]


async def test_add_item_validation(session_factory: Factory) -> None:
    s = await make(session_factory)
    with pytest.raises(ValidationFailed):
        await s.shop.add_item(GUILD.id, "  ", 10)
    with pytest.raises(ValidationFailed):
        await s.shop.add_item(GUILD.id, "Gratis", 0)
    await s.shop.add_item(GUILD.id, "Unik", 10)
    with pytest.raises(ValidationFailed):
        await s.shop.add_item(GUILD.id, "unik", 10)


async def test_autocomplete_search_is_prefix_based(session_factory: Factory) -> None:
    s = await make(session_factory)
    for name in ("Pedang", "Perisai", "Topi"):
        await s.shop.add_item(GUILD.id, name, 10)
    assert await s.shop.search_names(GUILD.id, "pe") == ["Pedang", "Perisai"]
    assert await s.shop.search_names(GUILD.id, "%") == []
