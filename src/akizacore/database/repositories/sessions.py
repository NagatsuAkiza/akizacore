from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import User, UserSession


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        id: str,
        user_id: int,
        access_token: str,
        refresh_token: str | None = None,
        scope: str = "identify guilds",
        expires_at: datetime,
    ) -> UserSession:
        user_session = UserSession(
            id=id,
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            scope=scope,
            expires_at=expires_at,
        )
        self.session.add(user_session)
        await self.session.flush()
        return user_session

    async def get(self, session_id: str) -> UserSession | None:
        return await self.session.get(UserSession, session_id, populate_existing=True)

    async def get_with_user(self, session_id: str) -> tuple[UserSession, User] | None:
        stmt = (
            select(UserSession, User)
            .join(User, UserSession.user_id == User.id)
            .where(UserSession.id == session_id)
        )
        res = await self.session.execute(stmt)
        row = res.first()
        if row is None:
            return None
        return row[0], row[1]

    async def delete(self, session_id: str) -> bool:
        stmt = delete(UserSession).where(UserSession.id == session_id)
        res = await self.session.execute(stmt)
        return bool(getattr(res, "rowcount", 0))

    async def delete_for_user(self, user_id: int) -> int:
        stmt = delete(UserSession).where(UserSession.user_id == user_id)
        res = await self.session.execute(stmt)
        return int(getattr(res, "rowcount", 0) or 0)

    async def update_last_seen(self, session_id: str) -> None:
        stmt = (
            update(UserSession).where(UserSession.id == session_id).values(last_seen_at=func.now())
        )
        await self.session.execute(stmt)

    async def update_cached_guilds(self, session_id: str, guilds: list[dict[str, Any]]) -> None:
        stmt = (
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(cached_guilds=guilds, guilds_cached_at=func.now())
        )
        await self.session.execute(stmt)
