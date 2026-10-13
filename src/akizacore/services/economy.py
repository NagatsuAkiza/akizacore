import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.core.exceptions import (
    InsufficientFunds,
    NotFound,
    PermissionDenied,
    QuotaExceeded,
    ValidationFailed,
)
from akizacore.database.repositories import EconomyRepository
from akizacore.database.session import session_scope
from akizacore.models import EconomyAccount
from akizacore.schemas.economy import (
    DailyResult,
    LeaderboardEntry,
    ProfileView,
    TransferResult,
    WorkResult,
    XpResult,
)
from akizacore.services.economy_config import EconomyConfig
from akizacore.services.levels import level_for_xp, level_progress
from akizacore.utils.snowflake import snowflake_to_datetime

JOBS: tuple[str, ...] = (
    "mengantar paket",
    "menjadi barista",
    "memperbaiki bug",
    "mengajar les",
    "menjaga warung",
    "menjadi kurir",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _XpOutcome:
    level: int
    leveled_up: bool
    bonus: int


class EconomyService:
    """Semua perubahan saldo lewat sini: saldo dan ledger selalu ditulis dalam satu transaksi.

    Konkurensi: baris akun dikunci (SELECT ... FOR UPDATE) sebelum cek aturan dan ubah saldo,
    sehingga cooldown, batas harian, dan saldo aman dari request paralel.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        config: EconomyConfig | None = None,
        clock: Callable[[], datetime] | None = None,
        mono: Callable[[], float] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._sf = session_factory
        self._cfg = config or EconomyConfig()
        self._clock = clock or _utc_now
        self._mono = mono or time.monotonic
        self._rng = rng or random.Random()
        self._xp_last: dict[tuple[int, int], float] = {}

    # ---------- Baca ----------
    async def balance(self, server_id: int, user_id: int) -> int:
        async with session_scope(self._sf) as session:
            return (await self._read(session, server_id, user_id)).balance

    async def profile(self, server_id: int, user_id: int) -> ProfileView:
        async with session_scope(self._sf) as session:
            account = await self._read(session, server_id, user_id)
            level, into, needed = level_progress(account.xp)
            return ProfileView(
                balance=account.balance,
                xp=account.xp,
                level=level,
                xp_into_level=into,
                xp_needed=needed,
            )

    async def leaderboard(
        self, server_id: int, *, by: str = "balance", limit: int = 10
    ) -> list[LeaderboardEntry]:
        if by not in ("balance", "xp"):
            raise ValidationFailed("Urutan leaderboard harus 'balance' atau 'xp'.")
        limit = max(1, min(limit, 25))
        async with session_scope(self._sf) as session:
            rows = await EconomyRepository(session).top(server_id, by_xp=by == "xp", limit=limit)
            return [
                LeaderboardEntry(
                    user_id=account.user_id,
                    username=name,
                    balance=account.balance,
                    xp=account.xp,
                    level=account.level,
                )
                for account, name in rows
            ]

    async def paginated_leaderboard(
        self, server_id: int, *, by: str = "balance", page: int = 1, limit: int = 20
    ) -> tuple[list[LeaderboardEntry], int]:
        if by not in ("balance", "xp"):
            raise ValidationFailed("Urutan leaderboard harus 'balance' atau 'xp'.")
        limit = max(1, min(limit, 100))
        page = max(1, page)
        offset = (page - 1) * limit
        async with session_scope(self._sf) as session:
            repo = EconomyRepository(session)
            total = await repo.count_accounts(server_id)
            rows = await repo.top(server_id, by_xp=by == "xp", limit=limit, offset=offset)
            items = [
                LeaderboardEntry(
                    user_id=account.user_id,
                    username=name,
                    balance=account.balance,
                    xp=account.xp,
                    level=account.level,
                )
                for account, name in rows
            ]
            return items, total

    # ---------- Ubah saldo dasar ----------
    async def charge(
        self,
        server_id: int,
        user_id: int,
        amount: int,
        *,
        kind: str,
        meta: dict[str, Any] | None = None,
    ) -> int:
        """Kurangi saldo. Return saldo setelahnya. Raise InsufficientFunds bila kurang."""
        self._check_amount(amount)
        async with session_scope(self._sf) as session:
            return await self.apply_in_session(session, server_id, user_id, -amount, kind, meta)

    async def credit(
        self,
        server_id: int,
        user_id: int,
        amount: int,
        *,
        kind: str,
        meta: dict[str, Any] | None = None,
    ) -> int:
        """Tambah saldo. Return saldo setelahnya."""
        self._check_amount(amount)
        async with session_scope(self._sf) as session:
            return await self.apply_in_session(session, server_id, user_id, amount, kind, meta)

    async def apply_in_session(
        self,
        session: AsyncSession,
        server_id: int,
        user_id: int,
        delta: int,
        kind: str,
        meta: dict[str, Any] | None = None,
    ) -> int:
        """Untuk service lain yang butuh ubah saldo di dalam unit of work miliknya (mis. shop)."""
        repo = EconomyRepository(session)
        account = await self._lock(repo, server_id, user_id)
        return await self._move(repo, account, delta, kind, meta)

    # ---------- Use case ----------
    async def daily(self, server_id: int, user_id: int) -> DailyResult:
        cfg = self._cfg
        now = self._clock()
        async with session_scope(self._sf) as session:
            repo = EconomyRepository(session)
            account = await self._lock(repo, server_id, user_id)
            if (
                not self._is_owner(user_id)
                and account.last_daily is not None
                and self._local_date(account.last_daily) >= self._local_date(now)
            ):
                raise QuotaExceeded(
                    f"Daily hari ini sudah diambil. Reset tengah malam {self._tz_label()}."
                )
            account.last_daily = now
            await self._move(repo, account, cfg.daily_amount, "daily", None)
            xp = await self._gain_xp(repo, account, cfg.daily_xp)
            return DailyResult(
                amount=cfg.daily_amount,
                balance=account.balance,
                xp_gained=cfg.daily_xp,
                level=xp.level,
                leveled_up=xp.leveled_up,
                bonus_coins=xp.bonus,
            )

    async def work(self, server_id: int, user_id: int) -> WorkResult:
        cfg = self._cfg
        now = self._clock()
        async with session_scope(self._sf) as session:
            repo = EconomyRepository(session)
            account = await self._lock(repo, server_id, user_id)
            last = await repo.last_transaction_at(server_id, user_id, "work")
            if last is not None and not self._is_owner(user_id):
                elapsed = (now - last).total_seconds()
                if elapsed < cfg.work_cooldown_s:
                    minutes = math.ceil((cfg.work_cooldown_s - elapsed) / 60)
                    raise QuotaExceeded(
                        f"Kamu masih lelah. Coba bekerja lagi dalam {minutes} menit."
                    )
            amount = self._rng.randint(cfg.work_min, cfg.work_max)
            job = self._rng.choice(JOBS)
            await self._move(repo, account, amount, "work", {"job": job})
            xp = await self._gain_xp(repo, account, cfg.work_xp)
            return WorkResult(
                job=job,
                amount=amount,
                balance=account.balance,
                xp_gained=cfg.work_xp,
                level=xp.level,
                leveled_up=xp.leveled_up,
                bonus_coins=xp.bonus,
            )

    async def transfer(
        self, server_id: int, sender_id: int, receiver_id: int, amount: int
    ) -> TransferResult:
        cfg = self._cfg
        if amount <= 0:
            raise ValidationFailed("Jumlah harus lebih dari 0.")
        if sender_id == receiver_id:
            raise ValidationFailed("Tidak bisa transfer ke diri sendiri.")
        now = self._clock()
        age_days = (now - snowflake_to_datetime(sender_id)).days
        if age_days < cfg.transfer_min_account_age_days and not self._is_owner(sender_id):
            raise PermissionDenied(
                f"Akun Discord kamu harus berumur minimal "
                f"{cfg.transfer_min_account_age_days} hari untuk transfer."
            )

        async with session_scope(self._sf) as session:
            repo = EconomyRepository(session)
            await self._ensure(repo, server_id, sender_id)
            await self._ensure(repo, server_id, receiver_id)
            # kunci berurutan berdasarkan ID agar dua transfer silang tidak deadlock
            accounts: dict[int, EconomyAccount] = {}
            for uid in sorted((sender_id, receiver_id)):
                locked = await repo.get_for_update(server_id, uid)
                if locked is None:
                    raise NotFound("Akun ekonomi tidak ditemukan.")
                accounts[uid] = locked

            sent_today = await repo.sum_out_since(
                server_id, sender_id, "transfer_out", self._local_day_start(now)
            )
            remaining = cfg.transfer_daily_limit - sent_today
            if amount > remaining and not self._is_owner(sender_id):
                raise QuotaExceeded(
                    f"Batas transfer harian {cfg.transfer_daily_limit} koin "
                    f"(sisa hari ini: {max(remaining, 0)})."
                )
            sender_balance = await self._move(
                repo, accounts[sender_id], -amount, "transfer_out", {"to": receiver_id}
            )
            receiver_balance = await self._move(
                repo, accounts[receiver_id], amount, "transfer_in", {"from": sender_id}
            )
            return TransferResult(
                amount=amount, sender_balance=sender_balance, receiver_balance=receiver_balance
            )

    # ---------- XP dari chat ----------
    def message_xp_ready(self, server_id: int, user_id: int) -> bool:
        """Cek murah (tanpa DB): apakah cooldown XP chat user ini sudah lewat."""
        if self._is_owner(user_id):
            return True
        last = self._xp_last.get((server_id, user_id))
        return last is None or self._mono() - last >= self._cfg.message_xp_cooldown_s

    async def award_message_xp(self, server_id: int, user_id: int) -> XpResult | None:
        if not self.message_xp_ready(server_id, user_id):
            return None
        self._remember_xp(server_id, user_id)
        amount = self._rng.randint(self._cfg.message_xp_min, self._cfg.message_xp_max)
        async with session_scope(self._sf) as session:
            repo = EconomyRepository(session)
            account = await self._lock(repo, server_id, user_id)
            outcome = await self._gain_xp(repo, account, amount)
            return XpResult(
                xp_gained=amount,
                level=outcome.level,
                leveled_up=outcome.leveled_up,
                bonus_coins=outcome.bonus,
            )

    def _remember_xp(self, server_id: int, user_id: int) -> None:
        now = self._mono()
        self._xp_last[(server_id, user_id)] = now
        if len(self._xp_last) > 10_000:  # jaga memori: buang entri yang cooldown-nya sudah lewat
            cooldown = self._cfg.message_xp_cooldown_s
            self._xp_last = {k: t for k, t in self._xp_last.items() if now - t < cooldown}

    def _is_owner(self, user_id: int) -> bool:
        return self._cfg.owner_user_id == user_id

    # ---------- Internal ----------
    @staticmethod
    def _check_amount(amount: int) -> None:
        if amount <= 0:
            raise ValidationFailed("Jumlah harus lebih dari 0.")

    async def _read(self, session: AsyncSession, server_id: int, user_id: int) -> EconomyAccount:
        repo = EconomyRepository(session)
        await self._ensure(repo, server_id, user_id)
        account = await repo.get(server_id, user_id)
        if account is None:
            raise NotFound("Akun ekonomi tidak ditemukan.")
        return account

    async def _ensure(self, repo: EconomyRepository, server_id: int, user_id: int) -> None:
        starter = self._cfg.starter_balance
        created = await repo.ensure_account(server_id, user_id, starter)
        if created and starter > 0:
            await repo.add_transaction(
                server_id, user_id, starter, "starter", starter, None, self._clock()
            )

    async def _lock(self, repo: EconomyRepository, server_id: int, user_id: int) -> EconomyAccount:
        await self._ensure(repo, server_id, user_id)
        account = await repo.get_for_update(server_id, user_id)
        if account is None:
            raise NotFound("Akun ekonomi tidak ditemukan.")
        return account

    async def _move(
        self,
        repo: EconomyRepository,
        account: EconomyAccount,
        delta: int,
        kind: str,
        meta: dict[str, Any] | None,
    ) -> int:
        new_balance = account.balance + delta
        if new_balance < 0:
            raise InsufficientFunds(
                f"Koin tidak cukup: butuh {-delta}, saldo kamu {account.balance}."
            )
        account.balance = new_balance
        await repo.add_transaction(
            account.server_id, account.user_id, delta, kind, new_balance, meta, self._clock()
        )
        return new_balance

    async def _gain_xp(
        self, repo: EconomyRepository, account: EconomyAccount, amount: int
    ) -> _XpOutcome:
        old_level = account.level
        account.xp += amount
        new_level = level_for_xp(account.xp)
        if new_level <= old_level:
            return _XpOutcome(level=old_level, leveled_up=False, bonus=0)
        account.level = new_level
        bonus = sum(level * 10 for level in range(old_level + 1, new_level + 1))
        await self._move(repo, account, bonus, "level_up", {"level": new_level})
        return _XpOutcome(level=new_level, leveled_up=True, bonus=bonus)

    def _tz(self) -> timezone:
        return timezone(timedelta(hours=self._cfg.utc_offset_hours))

    def _tz_label(self) -> str:
        return f"UTC{self._cfg.utc_offset_hours:+d}"

    def _local_date(self, moment: datetime) -> date:
        return moment.astimezone(self._tz()).date()

    def _local_day_start(self, moment: datetime) -> datetime:
        return moment.astimezone(self._tz()).replace(hour=0, minute=0, second=0, microsecond=0)
