import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.database.repositories import SessionRepository
from akizacore.database.session import session_scope
from akizacore.models import User, UserSession


class AuthService:
    """Manajemen sesi dan autentikasi dashboard."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create_session(
        self,
        *,
        user_id: int,
        access_token: str,
        refresh_token: str | None = None,
        scope: str = "identify guilds",
        ttl_s: int = 7 * 86400,
    ) -> UserSession:
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_s)
        async with session_scope(self._sf) as session:
            repo = SessionRepository(session)
            return await repo.create(
                id=session_id,
                user_id=user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                scope=scope,
                expires_at=expires_at,
            )

    async def get_session(self, session_id: str) -> UserSession | None:
        async with session_scope(self._sf) as session:
            sess = await SessionRepository(session).get(session_id)
            if sess is None or sess.expires_at <= datetime.now(UTC):
                return None
            return sess

    async def get_user_by_session(self, session_id: str) -> User | None:
        async with session_scope(self._sf) as session:
            repo = SessionRepository(session)
            res = await repo.get_with_user(session_id)
            if res is None:
                return None
            sess, user = res
            if sess.expires_at <= datetime.now(UTC):
                return None
            await repo.update_last_seen(session_id)
            return user

    async def revoke_session(self, session_id: str) -> bool:
        async with session_scope(self._sf) as session:
            return await SessionRepository(session).delete(session_id)
