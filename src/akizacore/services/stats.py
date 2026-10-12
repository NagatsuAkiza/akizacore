from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.database.repositories import AIUsageRepository, EconomyRepository
from akizacore.database.session import session_scope
from akizacore.schemas.stats import StatsView


class StatsService:
    """Statistik ringkas satu server (untuk admin)."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, utc_offset_hours: int = 7
    ) -> None:
        self._sf = session_factory
        self._offset = utc_offset_hours

    async def snapshot(self, server_id: int) -> StatsView:
        tz = timezone(timedelta(hours=self._offset))
        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        async with session_scope(self._sf) as session:
            accounts, coins = await EconomyRepository(session).stats(server_id)
            usage = AIUsageRepository(session)
            return StatsView(
                economy_accounts=accounts,
                coins_in_circulation=coins,
                ai_requests_today=await usage.count_since(today, server_id=server_id),
                ai_requests_7d=await usage.count_since(
                    today - timedelta(days=6), server_id=server_id
                ),
            )
