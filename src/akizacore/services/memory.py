from __future__ import annotations

import builtins

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.core.exceptions import NotFound, PermissionDenied, ValidationFailed
from akizacore.database.repositories import MemoryRepository, UserRepository
from akizacore.database.session import session_scope
from akizacore.models import Memory


class MemoryService:
    CONTENT_LIMIT = 500
    CONTEXT_LIMIT = 5
    CONTEXT_MAX_CHARS = 2000
    LIST_LIMIT = 20

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def save(self, server_id: int, user_id: int, content: str) -> Memory:
        normalized = content.strip()
        if not normalized:
            raise ValidationFailed("Memory tidak boleh kosong.")
        if len(normalized) > self.CONTENT_LIMIT:
            raise ValidationFailed("Memory terlalu panjang (maksimal 500 karakter).")

        async with session_scope(self._sf) as session:
            await self._require_ai_enabled(session, user_id)
            return await MemoryRepository(session).create(user_id, server_id, normalized)

    async def list(self, server_id: int, user_id: int, *, limit: int | None = None) -> list[Memory]:
        async with session_scope(self._sf) as session:
            return await MemoryRepository(session).list_for_user(
                user_id, server_id, min(limit or self.LIST_LIMIT, self.LIST_LIMIT)
            )

    async def delete(self, server_id: int, user_id: int, memory_id: int) -> None:
        async with session_scope(self._sf) as session:
            deleted = await MemoryRepository(session).delete_for_user(memory_id, user_id, server_id)
            if not deleted:
                raise NotFound("Memory tidak ditemukan.")

    async def clear(self, server_id: int, user_id: int) -> int:
        async with session_scope(self._sf) as session:
            return await MemoryRepository(session).clear_for_user(user_id, server_id)

    async def context_for_ai(self, server_id: int, user_id: int) -> builtins.list[Memory]:
        async with session_scope(self._sf) as session:
            await self._require_ai_enabled(session, user_id)
            rows = await MemoryRepository(session).list_for_user(
                user_id, server_id, self.CONTEXT_LIMIT
            )

        selected: list[Memory] = []
        chars = 0
        for row in rows:
            if chars + len(row.content) > self.CONTEXT_MAX_CHARS:
                break
            selected.append(row)
            chars += len(row.content)
        return selected

    @staticmethod
    async def _require_ai_enabled(session: AsyncSession, user_id: int) -> None:
        profile = await UserRepository(session).get_profile(user_id)
        if profile is not None and profile.ai_opt_out:
            raise PermissionDenied("Memory AI tidak tersedia karena kamu menonaktifkan fitur AI.")
