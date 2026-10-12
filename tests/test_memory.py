import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.core.exceptions import NotFound, PermissionDenied, ValidationFailed
from akizacore.models import UserProfile
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.services.container import Services

Factory = async_sessionmaker[AsyncSession]
GUILD = GuildInfo(id=1, name="G", owner_id=9)
OTHER_GUILD = GuildInfo(id=2, name="Other", owner_id=9)
USER = UserInfo(id=2, username="u")
OTHER_USER = UserInfo(id=3, username="other")


async def make(session_factory: Factory) -> Services:
    services = Services.build(session_factory)
    await services.onboarding.ensure_context(USER, GUILD)
    await services.onboarding.ensure_context(OTHER_USER, OTHER_GUILD)
    return services


async def test_save_list_delete_and_clear_are_scoped(session_factory: Factory) -> None:
    services = await make(session_factory)
    saved = await services.memory.save(GUILD.id, USER.id, " Saya suka jawaban singkat. ")
    assert saved.content == "Saya suka jawaban singkat."
    assert [item.id for item in await services.memory.list(GUILD.id, USER.id)] == [saved.id]
    await services.memory.delete(GUILD.id, USER.id, saved.id)
    assert await services.memory.list(GUILD.id, USER.id) == []
    await services.memory.save(GUILD.id, USER.id, "Hapus semua ini.")
    assert await services.memory.clear(GUILD.id, USER.id) == 1


async def test_memory_validation_and_scope(session_factory: Factory) -> None:
    services = await make(session_factory)
    with pytest.raises(ValidationFailed):
        await services.memory.save(GUILD.id, USER.id, "   ")
    with pytest.raises(ValidationFailed):
        await services.memory.save(GUILD.id, USER.id, "x" * 501)
    saved = await services.memory.save(GUILD.id, USER.id, "rahasia")
    assert await services.memory.list(OTHER_GUILD.id, USER.id) == []
    assert await services.memory.list(GUILD.id, OTHER_USER.id) == []
    with pytest.raises(NotFound):
        await services.memory.delete(OTHER_GUILD.id, USER.id, saved.id)
    with pytest.raises(NotFound):
        await services.memory.delete(GUILD.id, OTHER_USER.id, saved.id)


async def test_memory_ordering_and_limit(session_factory: Factory) -> None:
    services = await make(session_factory)
    for content in ("first", "second", "third"):
        await services.memory.save(GUILD.id, USER.id, content)
    assert [item.content for item in await services.memory.list(GUILD.id, USER.id, limit=2)] == [
        "third",
        "second",
    ]


async def test_opted_out_user_cannot_save_or_retrieve_but_can_clear(
    session_factory: Factory,
) -> None:
    services = await make(session_factory)
    async with session_factory() as session:
        await session.execute(
            update(UserProfile).where(UserProfile.user_id == USER.id).values(ai_opt_out=True)
        )
        await session.commit()
    with pytest.raises(PermissionDenied):
        await services.memory.save(GUILD.id, USER.id, "private")
    with pytest.raises(PermissionDenied):
        await services.memory.context_for_ai(GUILD.id, USER.id)
    assert await services.memory.clear(GUILD.id, USER.id) == 0
