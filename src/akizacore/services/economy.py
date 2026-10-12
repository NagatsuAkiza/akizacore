from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.core.exceptions import InsufficientFunds, NotFound, ValidationFailed
from akizacore.database.repositories import EconomyRepository
from akizacore.database.session import session_scope


class EconomyService:
    """Semua perubahan saldo lewat sini: saldo dan ledger ditulis dalam satu transaksi."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, starter_balance: int = 100
    ) -> None:
        self._sf = session_factory
        self._starter = starter_balance

    async def balance(self, server_id: int, user_id: int) -> int:
        async with session_scope(self._sf) as session:
            repo = EconomyRepository(session)
            await self._ensure(repo, server_id, user_id)
            account = await repo.get(server_id, user_id)
            if account is None:
                raise NotFound("Akun ekonomi tidak ditemukan.")
            return account.balance

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
            return await self._apply(session, server_id, user_id, -amount, kind, meta)

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
            return await self._apply(session, server_id, user_id, amount, kind, meta)

    @staticmethod
    def _check_amount(amount: int) -> None:
        if amount <= 0:
            raise ValidationFailed("Jumlah harus lebih dari 0.")

    async def _ensure(self, repo: EconomyRepository, server_id: int, user_id: int) -> None:
        created = await repo.ensure_account(server_id, user_id, self._starter)
        if created and self._starter > 0:
            await repo.add_transaction(server_id, user_id, self._starter, "starter", self._starter)

    async def _apply(
        self,
        session: AsyncSession,
        server_id: int,
        user_id: int,
        delta: int,
        kind: str,
        meta: dict[str, Any] | None,
    ) -> int:
        repo = EconomyRepository(session)
        await self._ensure(repo, server_id, user_id)
        account = await repo.get_for_update(server_id, user_id)
        if account is None:
            raise NotFound("Akun ekonomi tidak ditemukan.")
        new_balance = account.balance + delta
        if new_balance < 0:
            raise InsufficientFunds(
                f"Koin tidak cukup: butuh {-delta}, saldo kamu {account.balance}."
            )
        account.balance = new_balance
        await repo.add_transaction(server_id, user_id, delta, kind, new_balance, meta)
        return new_balance
