import pytest

from akizacore.cogs.ai.chat import _ConfirmationManager
from akizacore.core.exceptions import AkizaError


@pytest.mark.asyncio
async def test_confirmation_is_bound_to_actor_and_guild() -> None:
    manager = _ConfirmationManager()
    called = False

    async def callback() -> str:
        nonlocal called
        called = True
        return "done"

    token = manager.create(
        guild_id=10,
        actor_id=20,
        action="kick",
        callback=callback,
    )

    with pytest.raises(AkizaError, match="bukan milik"):
        await manager.consume(token=token, guild_id=10, actor_id=21)
    assert not called
    assert await manager.consume(token=token, guild_id=10, actor_id=20) == "done"
    assert called

    with pytest.raises(AkizaError, match="tidak valid"):
        await manager.consume(token=token, guild_id=10, actor_id=20)


@pytest.mark.asyncio
async def test_confirmation_expires() -> None:
    manager = _ConfirmationManager()

    async def callback() -> str:
        return "done"

    token = manager.create(
        guild_id=10,
        actor_id=20,
        action="ban",
        callback=callback,
    )
    manager._pending[token].created_at -= 121
    with pytest.raises(AkizaError, match="tidak valid"):
        await manager.consume(token=token, guild_id=10, actor_id=20)
