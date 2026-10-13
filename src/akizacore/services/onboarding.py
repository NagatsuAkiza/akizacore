from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.database.repositories import ServerRepository, SettingsRepository, UserRepository
from akizacore.database.session import session_scope
from akizacore.models import Server
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.schemas.settings import DEFAULT_FEATURES


class OnboardingService:
    """Mendaftarkan guild dan user ke database (idempotent, aman dipanggil berulang)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def register_guild(self, guild: GuildInfo) -> None:
        async with session_scope(self._sf) as session:
            await self._register_guild(session, guild)

    async def sync_guilds(self, guilds: Sequence[GuildInfo]) -> None:
        async with session_scope(self._sf) as session:
            for guild in guilds:
                await self._register_guild(session, guild)

    async def deactivate_guild(self, guild_id: int) -> None:
        async with session_scope(self._sf) as session:
            await ServerRepository(session).deactivate(guild_id)

    async def get_active_server_ids(self, server_ids: list[int] | None = None) -> set[int]:
        async with session_scope(self._sf) as session:
            return await ServerRepository(session).get_active_ids(server_ids)

    async def get_server(self, server_id: int) -> Server | None:
        async with session_scope(self._sf) as session:
            return await ServerRepository(session).get(server_id)

    async def ensure_user(self, user: UserInfo) -> None:
        async with session_scope(self._sf) as session:
            await self._ensure_user(session, user)

    async def ensure_context(self, user: UserInfo, guild: GuildInfo | None) -> None:
        """Dipanggil sebelum setiap command: pastikan user (dan guild) ada di database."""
        async with session_scope(self._sf) as session:
            await self._ensure_user(session, user)
            if guild is not None:
                await self._register_guild(session, guild)

    @staticmethod
    async def _register_guild(session: AsyncSession, guild: GuildInfo) -> None:
        await ServerRepository(session).upsert(guild.id, guild.name, guild.owner_id)
        await SettingsRepository(session).ensure(guild.id, dict(DEFAULT_FEATURES))

    @staticmethod
    async def _ensure_user(session: AsyncSession, user: UserInfo) -> None:
        repo = UserRepository(session)
        await repo.upsert(user.id, user.username, user.avatar, user.global_name)
        await repo.ensure_profile(user.id)
