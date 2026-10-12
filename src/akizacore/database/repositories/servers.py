from sqlalchemy import func, or_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import Server


class ServerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, server_id: int) -> Server | None:
        return await self.session.get(Server, server_id, populate_existing=True)

    async def upsert(self, server_id: int, name: str, owner_id: int | None) -> None:
        """Daftarkan server; bila sudah ada, perbarui nama/owner dan aktifkan kembali."""
        stmt = insert(Server).values(id=server_id, name=name, owner_id=owner_id, is_active=True)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Server.id],
            set_={
                "name": stmt.excluded.name,
                "owner_id": stmt.excluded.owner_id,
                "is_active": True,
                "updated_at": func.now(),
            },
            where=or_(
                Server.name != stmt.excluded.name,
                Server.owner_id.is_distinct_from(stmt.excluded.owner_id),
                Server.is_active.is_(False),
            ),
        )
        await self.session.execute(stmt)

    async def deactivate(self, server_id: int) -> None:
        await self.session.execute(
            update(Server).where(Server.id == server_id).values(is_active=False)
        )
