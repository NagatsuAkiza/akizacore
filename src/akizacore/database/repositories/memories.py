from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import Memory


class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: int, server_id: int, content: str) -> Memory:
        memory = Memory(user_id=user_id, server_id=server_id, content=content)
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def list_for_user(self, user_id: int, server_id: int, limit: int) -> list[Memory]:
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id, Memory.server_id == server_id)
            .order_by(Memory.id.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_for_user(self, memory_id: int, user_id: int, server_id: int) -> Memory | None:
        stmt = select(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == user_id,
            Memory.server_id == server_id,
        )
        return await self.session.scalar(stmt)

    async def delete_for_user(self, memory_id: int, user_id: int, server_id: int) -> bool:
        stmt = delete(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == user_id,
            Memory.server_id == server_id,
        )
        result = await self.session.execute(stmt)
        return bool(getattr(result, "rowcount", 0))

    async def clear_for_user(self, user_id: int, server_id: int) -> int:
        stmt = delete(Memory).where(Memory.user_id == user_id, Memory.server_id == server_id)
        result = await self.session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)
