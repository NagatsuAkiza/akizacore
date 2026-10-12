from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models.moderation import AutomodConfig, ModerationLog, ModWarning


class ModerationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_warning(
        self, *, server_id: int, user_id: int, mod_id: int, reason: str
    ) -> ModWarning:
        row = ModWarning(server_id=server_id, user_id=user_id, mod_id=mod_id, reason=reason)
        self.session.add(row)
        await self.session.flush()
        return row

    async def active_warnings(
        self, server_id: int, user_id: int, limit: int | None = None
    ) -> list[ModWarning]:
        stmt = (
            select(ModWarning)
            .where(
                ModWarning.server_id == server_id,
                ModWarning.user_id == user_id,
                ModWarning.active.is_(True),
            )
            .order_by(ModWarning.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list((await self.session.execute(stmt)).scalars())

    async def count_active(self, server_id: int, user_id: int) -> int:
        return len(await self.active_warnings(server_id, user_id))

    async def clear_warnings(self, server_id: int, user_id: int) -> int:
        result = await self.session.execute(
            update(ModWarning)
            .where(
                ModWarning.server_id == server_id,
                ModWarning.user_id == user_id,
                ModWarning.active.is_(True),
            )
            .values(active=False)
        )
        return max(int(getattr(result, "rowcount", 0) or 0), 0)

    async def add_log(
        self,
        *,
        server_id: int,
        target_id: int,
        mod_id: int | None,
        action: str,
        reason: str,
    ) -> None:
        self.session.add(
            ModerationLog(
                server_id=server_id,
                target_id=target_id,
                mod_id=mod_id,
                action=action,
                reason=reason,
            )
        )
        await self.session.flush()

    async def recent_logs(
        self, server_id: int, *, limit: int, target_id: int | None = None
    ) -> list[ModerationLog]:
        stmt = select(ModerationLog).where(ModerationLog.server_id == server_id)
        if target_id is not None:
            stmt = stmt.where(ModerationLog.target_id == target_id)
        stmt = stmt.order_by(ModerationLog.id.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars())

    async def get_automod(self, server_id: int) -> AutomodConfig | None:
        return await self.session.get(AutomodConfig, server_id)

    async def upsert_automod(self, server_id: int, **changes: object) -> AutomodConfig:
        row = await self.get_automod(server_id)
        if row is None:
            row = AutomodConfig(server_id=server_id)
            self.session.add(row)
        for key, value in changes.items():
            setattr(row, key, value)
        await self.session.flush()
        return row
