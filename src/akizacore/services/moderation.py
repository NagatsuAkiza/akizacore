import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.database.repositories.moderation import ModerationRepository
from akizacore.database.session import session_scope
from akizacore.models.moderation import AutomodConfig
from akizacore.schemas.moderation import AutomodView, ModLogView, WarningView, WarnResult

ACTIONS = ("delete", "warn", "timeout")
_EDITABLE = {"anti_spam", "spam_messages", "anti_link", "allowed_domains", "action"}
_MAX_REASON = 500


@dataclass(frozen=True, slots=True)
class ModerationConfig:
    warn_timeout_at: int = 3  # jumlah warn aktif sebelum auto-timeout
    warn_timeout_minutes: int = 60


def _clip(reason: str) -> str:
    return reason.strip()[:_MAX_REASON] or "Tanpa alasan"


def _normalize_domains(value: str | Iterable[str]) -> str:
    parts = re.split(r"[,\s]+", value) if isinstance(value, str) else list(value)
    cleaned = [p.strip().lower().removeprefix("www.") for p in parts if p and p.strip()]
    return ",".join(dict.fromkeys(cleaned))


def _to_view(row: AutomodConfig | None, server_id: int) -> AutomodView:
    if row is None:
        return AutomodView(server_id=server_id)
    return AutomodView(
        server_id=server_id,
        anti_spam=row.anti_spam,
        spam_messages=row.spam_messages,
        spam_window_s=row.spam_window_s,
        anti_link=row.anti_link,
        allowed_domains=tuple(d for d in row.allowed_domains.split(",") if d),
        action=row.action,
        timeout_minutes=row.timeout_minutes,
    )


class ModerationService:
    """Warn, log moderasi, dan pengaturan automod. Tidak tahu apa-apa soal Discord."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        config: ModerationConfig | None = None,
        cache_ttl_s: float = 15.0,
    ) -> None:
        self._sf = session_factory
        self.config = config or ModerationConfig()
        self._ttl = cache_ttl_s
        self._cache: dict[int, tuple[float, AutomodView]] = {}

    async def warn(self, *, server_id: int, user_id: int, mod_id: int, reason: str) -> WarnResult:
        text = _clip(reason)
        async with session_scope(self._sf) as session:
            repo = ModerationRepository(session)
            row = await repo.add_warning(
                server_id=server_id, user_id=user_id, mod_id=mod_id, reason=text
            )
            total = await repo.count_active(server_id, user_id)
            await repo.add_log(
                server_id=server_id, target_id=user_id, mod_id=mod_id, action="warn", reason=text
            )
            return WarnResult(row.id, total, total >= self.config.warn_timeout_at)

    async def warnings(self, server_id: int, user_id: int, limit: int = 10) -> list[WarningView]:
        async with session_scope(self._sf) as session:
            rows = await ModerationRepository(session).active_warnings(server_id, user_id, limit)
            return [WarningView(r.id, r.mod_id, r.reason, r.created_at) for r in rows]

    async def clear_warnings(self, *, server_id: int, user_id: int, mod_id: int) -> int:
        async with session_scope(self._sf) as session:
            repo = ModerationRepository(session)
            count = await repo.clear_warnings(server_id, user_id)
            if count:
                await repo.add_log(
                    server_id=server_id,
                    target_id=user_id,
                    mod_id=mod_id,
                    action="clearwarns",
                    reason=f"{count} warn dihapus",
                )
            return count

    async def log_action(
        self, *, server_id: int, target_id: int, mod_id: int | None, action: str, reason: str
    ) -> None:
        async with session_scope(self._sf) as session:
            await ModerationRepository(session).add_log(
                server_id=server_id,
                target_id=target_id,
                mod_id=mod_id,
                action=action[:32],
                reason=_clip(reason),
            )

    async def recent_logs(
        self, server_id: int, *, limit: int = 10, target_id: int | None = None
    ) -> list[ModLogView]:
        async with session_scope(self._sf) as session:
            rows = await ModerationRepository(session).recent_logs(
                server_id, limit=limit, target_id=target_id
            )
            return [
                ModLogView(r.id, r.target_id, r.mod_id, r.action, r.reason, r.created_at)
                for r in rows
            ]

    async def get_automod(self, server_id: int) -> AutomodView:
        cached = self._cache.get(server_id)
        if cached is not None and time.monotonic() - cached[0] < self._ttl:
            return cached[1]
        async with session_scope(self._sf) as session:
            view = _to_view(await ModerationRepository(session).get_automod(server_id), server_id)
        self._cache[server_id] = (time.monotonic(), view)
        return view

    async def set_automod(self, server_id: int, **changes: Any) -> AutomodView:
        unknown = set(changes) - _EDITABLE
        if unknown:
            raise ValueError(f"Pengaturan tidak dikenal: {sorted(unknown)}")
        if "action" in changes and changes["action"] not in ACTIONS:
            raise ValueError(f"action harus salah satu dari {ACTIONS}")
        if "allowed_domains" in changes:
            changes["allowed_domains"] = _normalize_domains(changes["allowed_domains"])
        async with session_scope(self._sf) as session:
            row = await ModerationRepository(session).upsert_automod(server_id, **changes)
            view = _to_view(row, server_id)
        self._cache.pop(server_id, None)
        return view
