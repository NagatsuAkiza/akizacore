from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import ServerSettings


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, server_id: int) -> ServerSettings | None:
        return await self.session.get(ServerSettings, server_id, populate_existing=True)

    async def ensure(self, server_id: int, features: dict[str, bool]) -> None:
        """Buat baris settings bila belum ada. Tidak menimpa konfigurasi yang sudah ada."""
        stmt = (
            insert(ServerSettings)
            .values(server_id=server_id, features=features)
            .on_conflict_do_nothing(index_elements=[ServerSettings.server_id])
        )
        await self.session.execute(stmt)

    async def update(self, server_id: int, values: dict[str, Any]) -> ServerSettings | None:
        row = await self.get(server_id)
        if row is None:
            return None
        for key, value in values.items():
            setattr(row, key, value)
        await self.session.flush()
        return row
