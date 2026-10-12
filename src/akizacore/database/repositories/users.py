from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import User, UserProfile


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id, populate_existing=True)

    async def upsert(self, user_id: int, username: str, avatar: str | None) -> None:
        stmt = insert(User).values(id=user_id, username=username, avatar=avatar)
        stmt = stmt.on_conflict_do_update(
            index_elements=[User.id],
            set_={
                "username": stmt.excluded.username,
                "avatar": stmt.excluded.avatar,
                "updated_at": func.now(),
            },
            # hanya tulis bila ada yang berubah (hemat write di tiap command)
            where=or_(
                User.username != stmt.excluded.username,
                User.avatar.is_distinct_from(stmt.excluded.avatar),
            ),
        )
        await self.session.execute(stmt)

    async def ensure_profile(self, user_id: int) -> None:
        stmt = (
            insert(UserProfile)
            .values(user_id=user_id)
            .on_conflict_do_nothing(index_elements=[UserProfile.user_id])
        )
        await self.session.execute(stmt)

    async def get_profile(self, user_id: int) -> UserProfile | None:
        return await self.session.get(UserProfile, user_id, populate_existing=True)
