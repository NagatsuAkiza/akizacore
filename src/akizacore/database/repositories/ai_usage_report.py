from datetime import datetime

from sqlalchemy import ColumnElement, DateTime, and_, cast, func, literal_column, select
from sqlalchemy import Date as SqlDate
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import AIUsage, User
from akizacore.schemas.ai_usage import (
    DailyUsage,
    ErrorEntry,
    NamedCount,
    UsageTotals,
    UserUsage,
)

_LLM_OK = and_(AIUsage.status == "ok", AIUsage.kind != "rule")
_TOKENS = AIUsage.prompt_tokens + AIUsage.completion_tokens


def _filters(
    since: datetime, server_id: int | None, user_id: int | None
) -> list[ColumnElement[bool]]:
    conditions = [AIUsage.created_at >= since]
    if server_id is not None:
        conditions.append(AIUsage.server_id == server_id)
    if user_id is not None:
        conditions.append(AIUsage.user_id == user_id)
    return conditions


class AIUsageReportRepository:
    """Query agregat untuk tracking pemakaian AI (baca-saja)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def totals(
        self, since: datetime, *, server_id: int | None = None, user_id: int | None = None
    ) -> UsageTotals:
        stmt = select(
            func.count().filter(_LLM_OK),
            func.count().filter(and_(AIUsage.status == "ok", AIUsage.kind == "rule")),
            func.count().filter(AIUsage.status == "error"),
            func.coalesce(func.sum(AIUsage.prompt_tokens), 0),
            func.coalesce(func.sum(AIUsage.completion_tokens), 0),
            func.coalesce(func.sum(AIUsage.coins), 0),
            func.avg(AIUsage.latency_ms).filter(_LLM_OK),
            func.percentile_cont(0.95).within_group(AIUsage.latency_ms).filter(_LLM_OK),
            func.count().filter(AIUsage.status == "rejected"),
        ).where(*_filters(since, server_id, user_id))
        row = (await self.session.execute(stmt)).one()
        return UsageTotals(
            requests=int(row[0]),
            rule_hits=int(row[1]),
            errors=int(row[2]),
            prompt_tokens=int(row[3]),
            completion_tokens=int(row[4]),
            coins=int(row[5]),
            avg_latency_ms=round(row[6]) if row[6] is not None else None,
            p95_latency_ms=round(row[7]) if row[7] is not None else None,
            rejected=int(row[8]),
        )

    async def daily(
        self, since: datetime, *, server_id: int, utc_offset_hours: int
    ) -> list[DailyUsage]:
        # Hari lokal = tanggal UTC digeser offset. Offset ditulis literal agar ekspresi SELECT
        # dan GROUP BY identik (parameter terikat akan dianggap ekspresi berbeda oleh PostgreSQL).
        local = func.timezone("UTC", AIUsage.created_at, type_=DateTime()) + literal_column(
            f"interval '{int(utc_offset_hours)} hours'"
        )
        day = cast(local, SqlDate)
        stmt = (
            select(
                day.label("day"),
                func.count().filter(_LLM_OK),
                func.count().filter(AIUsage.status == "error"),
                func.coalesce(func.sum(_TOKENS), 0),
                func.coalesce(func.sum(AIUsage.coins), 0),
            )
            .where(*_filters(since, server_id, None))
            .group_by(day)
            .order_by(day)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            DailyUsage(
                day=r[0], requests=int(r[1]), errors=int(r[2]), tokens=int(r[3]), coins=int(r[4])
            )
            for r in rows
        ]

    async def top_users(self, since: datetime, *, server_id: int, limit: int) -> list[UserUsage]:
        stmt = (
            select(
                AIUsage.user_id,
                User.username,
                func.count(),
                func.coalesce(func.sum(_TOKENS), 0),
                func.coalesce(func.sum(AIUsage.coins), 0),
            )
            .join(User, User.id == AIUsage.user_id)
            .where(*_filters(since, server_id, None), _LLM_OK)
            .group_by(AIUsage.user_id, User.username)
            .order_by(func.count().desc(), AIUsage.user_id)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            UserUsage(
                user_id=str(r[0]),
                username=r[1],
                requests=int(r[2]),
                tokens=int(r[3]),
                coins=int(r[4]),
            )
            for r in rows
        ]

    async def by_model(self, since: datetime, *, server_id: int) -> list[NamedCount]:
        stmt = (
            select(AIUsage.model, func.count(), func.coalesce(func.sum(_TOKENS), 0))
            .where(*_filters(since, server_id, None), _LLM_OK)
            .group_by(AIUsage.model)
            .order_by(func.count().desc(), AIUsage.model)
        )
        rows = (await self.session.execute(stmt)).all()
        return [NamedCount(name=r[0], requests=int(r[1]), tokens=int(r[2])) for r in rows]

    async def by_kind(self, since: datetime, *, server_id: int) -> list[NamedCount]:
        stmt = (
            select(AIUsage.kind, func.count(), func.coalesce(func.sum(_TOKENS), 0))
            .where(*_filters(since, server_id, None), AIUsage.status == "ok")
            .group_by(AIUsage.kind)
            .order_by(func.count().desc(), AIUsage.kind)
        )
        rows = (await self.session.execute(stmt)).all()
        return [NamedCount(name=r[0], requests=int(r[1]), tokens=int(r[2])) for r in rows]

    async def tools(self, since: datetime, *, server_id: int, limit: int) -> list[NamedCount]:
        exploded = (
            select(func.unnest(func.string_to_array(AIUsage.tools, ",")).label("tool"))
            .where(*_filters(since, server_id, None), AIUsage.status == "ok", AIUsage.tools != "")
            .subquery()
        )
        stmt = (
            select(exploded.c.tool, func.count())
            .group_by(exploded.c.tool)
            .order_by(func.count().desc(), exploded.c.tool)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [NamedCount(name=r[0], requests=int(r[1])) for r in rows]

    async def recent_errors(
        self, since: datetime, *, server_id: int, limit: int
    ) -> list[ErrorEntry]:
        stmt = (
            select(AIUsage)
            .where(*_filters(since, server_id, None), AIUsage.status == "error")
            .order_by(AIUsage.id.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            ErrorEntry(
                id=r.id,
                created_at=r.created_at,
                user_id=str(r.user_id),
                kind=r.kind,
                error_code=r.error_code,
                latency_ms=r.latency_ms,
            )
            for r in rows
        ]
