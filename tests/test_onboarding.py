from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.models import Server, UserProfile
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.schemas.settings import SettingsUpdate
from akizacore.services.container import Services

Factory = async_sessionmaker[AsyncSession]
GUILD = GuildInfo(id=111, name="Server A", owner_id=222)


async def test_register_guild_creates_server_and_default_settings(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.register_guild(GUILD)

    settings = await services.settings.get(GUILD.id)
    assert settings.features["ai"] is False
    assert settings.features["economy"] is True


async def test_register_guild_is_idempotent_and_keeps_settings(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.register_guild(GUILD)
    await services.settings.update(GUILD.id, SettingsUpdate(log_channel_id=999))

    await services.onboarding.register_guild(GuildInfo(id=111, name="Nama Baru", owner_id=222))

    settings = await services.settings.get(GUILD.id)
    assert settings.log_channel_id == 999
    async with session_factory() as session:
        server = await session.get(Server, GUILD.id)
        assert server is not None
        assert server.name == "Nama Baru"


async def test_deactivate_then_rejoin_reactivates(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.register_guild(GUILD)
    await services.onboarding.deactivate_guild(GUILD.id)
    async with session_factory() as session:
        server = await session.get(Server, GUILD.id)
        assert server is not None and server.is_active is False

    await services.onboarding.register_guild(GUILD)
    async with session_factory() as session:
        server = await session.get(Server, GUILD.id, populate_existing=True)
        assert server is not None and server.is_active is True


async def test_ensure_user_creates_profile_with_defaults(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    user = UserInfo(id=555, username="tester", avatar=None)
    await services.onboarding.ensure_user(user)
    await services.onboarding.ensure_user(user)  # kedua kali tidak boleh error

    async with session_factory() as session:
        profile = await session.get(UserProfile, 555)
        assert profile is not None
        assert profile.language == "id"
        assert profile.ai_opt_out is False


async def test_ensure_context_registers_user_and_guild(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.ensure_context(UserInfo(id=1, username="a"), GUILD)
    assert (await services.settings.get(GUILD.id)).server_id == GUILD.id
