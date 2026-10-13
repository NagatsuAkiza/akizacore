from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import EconomyAccount, Transaction, User


class EconomyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_account(self, server_id: int, user_id: int, starter_balance: int) -> bool:
        """Buat akun bila belum ada. Return True bila akun baru dibuat."""
        stmt = (
            insert(EconomyAccount)
            .values(server_id=server_id, user_id=user_id, balance=starter_balance)
            .on_conflict_do_nothing(
                index_elements=[EconomyAccount.server_id, EconomyAccount.user_id]
            )
            .returning(EconomyAccount.user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get(self, server_id: int, user_id: int) -> EconomyAccount | None:
        return await self.session.get(EconomyAccount, (server_id, user_id), populate_existing=True)

    async def get_for_update(self, server_id: int, user_id: int) -> EconomyAccount | None:
        """Kunci baris akun selama transaksi (cegah race saat ubah saldo)."""
        stmt = (
            select(EconomyAccount)
            .where(EconomyAccount.server_id == server_id, EconomyAccount.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_transaction(
        self,
        server_id: int,
        user_id: int,
        amount: int,
        kind: str,
        balance_after: int,
        meta: dict[str, Any] | None,
        created_at: datetime,
    ) -> None:
        self.session.add(
            Transaction(
                server_id=server_id,
                user_id=user_id,
                amount=amount,
                kind=kind,
                balance_after=balance_after,
                meta=meta or {},
                created_at=created_at,
            )
        )
        await self.session.flush()

    async def last_transaction_at(self, server_id: int, user_id: int, kind: str) -> datetime | None:
        stmt = (
            select(Transaction.created_at)
            .where(
                Transaction.server_id == server_id,
                Transaction.user_id == user_id,
                Transaction.kind == kind,
            )
            .order_by(Transaction.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def sum_out_since(self, server_id: int, user_id: int, kind: str, since: datetime) -> int:
        """Total koin keluar (nilai positif) untuk satu jenis transaksi sejak waktu tertentu."""
        stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.server_id == server_id,
            Transaction.user_id == user_id,
            Transaction.kind == kind,
            Transaction.created_at >= since,
        )
        return -int((await self.session.execute(stmt)).scalar_one())

    async def stats(self, server_id: int) -> tuple[int, int]:
        """Return (jumlah akun, total koin beredar) untuk satu server."""
        stmt = select(func.count(), func.coalesce(func.sum(EconomyAccount.balance), 0)).where(
            EconomyAccount.server_id == server_id
        )
        row = (await self.session.execute(stmt)).one()
        return int(row[0]), int(row[1])

    async def count_transactions_since(self, server_id: int, since: datetime) -> int:
        stmt = select(func.count(Transaction.id)).where(
            Transaction.server_id == server_id,
            Transaction.created_at >= since,
        )
        return int((await self.session.execute(stmt)).scalar_one() or 0)

    async def count_accounts(self, server_id: int) -> int:
        stmt = select(func.count(EconomyAccount.user_id)).where(
            EconomyAccount.server_id == server_id
        )
        return int((await self.session.execute(stmt)).scalar_one() or 0)

    async def top(
        self, server_id: int, *, by_xp: bool, limit: int, offset: int = 0
    ) -> list[tuple[EconomyAccount, str]]:
        order = EconomyAccount.xp.desc() if by_xp else EconomyAccount.balance.desc()
        stmt = (
            select(EconomyAccount, User.username)
            .join(User, User.id == EconomyAccount.user_id)
            .where(EconomyAccount.server_id == server_id)
            .order_by(order, EconomyAccount.user_id)
            .offset(offset)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]
