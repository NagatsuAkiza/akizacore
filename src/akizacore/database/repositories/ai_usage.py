from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import AIUsage


class AIUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        server_id: int,
        user_id: int,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        coins: int,
        kind: str = "ask",
        status: str = "ok",
        latency_ms: int | None = None,
        tools: tuple[str, ...] = (),
        error_code: str | None = None,
    ) -> None:
        self.session.add(
            AIUsage(
                server_id=server_id,
                user_id=user_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                coins=coins,
                kind=kind,
                status=status,
                latency_ms=latency_ms,
                tools=",".join(tools)[:200],
                error_code=error_code,
            )
        )
        await self.session.flush()

    async def count_since(
        self, since: datetime, *, user_id: int | None = None, server_id: int | None = None
    ) -> int:
        # Kuota hanya menghitung panggilan LLM yang berhasil (bukan error dan bukan jawaban rule).
        stmt = (
            select(func.count())
            .select_from(AIUsage)
            .where(
                AIUsage.created_at >= since,
                AIUsage.status == "ok",
                AIUsage.kind != "rule",
            )
        )
        if user_id is not None:
            stmt = stmt.where(AIUsage.user_id == user_id)
        if server_id is not None:
            stmt = stmt.where(AIUsage.server_id == server_id)
        return (await self.session.execute(stmt)).scalar_one()
