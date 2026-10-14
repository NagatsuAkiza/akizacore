from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.database.repositories import AIUsageRepository
from akizacore.database.repositories.ai_usage_report import AIUsageReportRepository
from akizacore.database.session import session_scope
from akizacore.schemas.ai_usage import DailyUsage, MyUsage, ServerUsageReport

MAX_DAYS = 90


class AIUsageService:
    """Tracking pemakaian AI: laporan per server dan pemakaian pribadi. Tidak tahu soal Discord."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        daily_user_limit: int,
        daily_global_limit: int,
        utc_offset_hours: int,
    ) -> None:
        self._sf = session_factory
        self._user_limit = daily_user_limit
        self._global_limit = daily_global_limit
        self._offset = utc_offset_hours

    def _day_start(self) -> datetime:
        # Sama dengan batas hari pada kuota di AIOrchestrator.
        tz = timezone(timedelta(hours=self._offset))
        return datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)

    async def server_report(
        self, server_id: int, *, days: int = 7, top_limit: int = 5, error_limit: int = 10
    ) -> ServerUsageReport:
        days = max(1, min(days, MAX_DAYS))
        since = self._day_start() - timedelta(days=days - 1)
        async with session_scope(self._sf) as session:
            repo = AIUsageReportRepository(session)
            totals = await repo.totals(since, server_id=server_id)
            daily_rows = await repo.daily(since, server_id=server_id, utc_offset_hours=self._offset)
            top_users = await repo.top_users(since, server_id=server_id, limit=top_limit)
            by_model = await repo.by_model(since, server_id=server_id)
            by_kind = await repo.by_kind(since, server_id=server_id)
            tools = await repo.tools(since, server_id=server_id, limit=10)
            errors = await repo.recent_errors(since, server_id=server_id, limit=error_limit)

        # Isi hari tanpa pemakaian dengan nol supaya grafik berkesinambungan.
        by_day = {row.day: row for row in daily_rows}
        first = since.date()
        daily = [
            by_day.get(first + timedelta(days=i), DailyUsage(day=first + timedelta(days=i)))
            for i in range(days)
        ]
        return ServerUsageReport(
            days=days,
            since=since,
            totals=totals,
            daily=daily,
            top_users=top_users,
            by_model=by_model,
            by_kind=by_kind,
            tools=tools,
            recent_errors=errors,
        )

    async def my_usage(self, user_id: int) -> MyUsage:
        today = self._day_start()
        async with session_scope(self._sf) as session:
            quota = AIUsageRepository(session)
            repo = AIUsageReportRepository(session)
            used_today = await quota.count_since(today, user_id=user_id)
            global_used = await quota.count_since(today)
            today_totals = await repo.totals(today, user_id=user_id)
            week = await repo.totals(today - timedelta(days=6), user_id=user_id)
        return MyUsage(
            used_today=used_today,
            user_limit=self._user_limit,
            global_used_today=global_used,
            global_limit=self._global_limit,
            tokens_today=today_totals.prompt_tokens + today_totals.completion_tokens,
            coins_today=today_totals.coins,
            last_7_days=week,
        )
