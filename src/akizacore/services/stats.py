from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.database.repositories import (
    AIUsageRepository,
    ConversationRepository,
    EconomyRepository,
    ModerationRepository,
)
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
            econ_repo = EconomyRepository(session)
            accounts, coins = await econ_repo.stats(server_id)
            usage = AIUsageRepository(session)
            ai_today = await usage.count_since(today, server_id=server_id)
            ai_7d = await usage.count_since(today - timedelta(days=6), server_id=server_id)

            conv_repo = ConversationRepository(session)
            total_messages = await conv_repo.count_messages_for_server(server_id)

            tx_today = await econ_repo.count_transactions_since(server_id, today)

            mod_repo = ModerationRepository(session)
            active_warnings = await mod_repo.count_active_warnings(server_id)
            mod_today = await mod_repo.count_logs(server_id, since=today)

            return StatsView(
                economy_accounts=accounts,
                coins_in_circulation=coins,
                ai_requests_today=ai_today,
                ai_requests_7d=ai_7d,
                member_count=accounts,
                total_messages=total_messages,
                ai_queries_today=ai_today,
                economy_transactions_today=tx_today,
                active_warnings=active_warnings,
                mod_actions_today=mod_today,
            )
