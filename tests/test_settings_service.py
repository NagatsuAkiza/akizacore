import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.core.exceptions import NotFound, ValidationFailed
from akizacore.schemas.discord import GuildInfo
from akizacore.schemas.settings import SettingsUpdate
from akizacore.services.container import Services

Factory = async_sessionmaker[AsyncSession]
GUILD = GuildInfo(id=10, name="Test", owner_id=1)


async def test_update_channels(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.register_guild(GUILD)

    result = await services.settings.update(
        GUILD.id, SettingsUpdate(log_channel_id=1, autorole_id=2)
    )
    assert result.log_channel_id == 1
    assert result.autorole_id == 2
    assert result.welcome_channel_id is None


async def test_set_feature_toggles_only_that_feature(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.register_guild(GUILD)

    result = await services.settings.set_feature(GUILD.id, "ai", True)
    assert result.features["ai"] is True
    assert result.features["economy"] is True


async def test_set_feature_rejects_unknown_feature(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.register_guild(GUILD)
    with pytest.raises(ValidationFailed):
        await services.settings.set_feature(GUILD.id, "tidak-ada", True)


async def test_get_unknown_server_raises_not_found(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    with pytest.raises(NotFound):
        await services.settings.get(424242)
