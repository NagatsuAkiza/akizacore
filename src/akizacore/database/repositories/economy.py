from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import EconomyAccount, Transaction


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
        """Kunci baris akun selama transaksi (cegah race saat potong/tambah saldo)."""
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
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            Transaction(
                server_id=server_id,
                user_id=user_id,
                amount=amount,
                kind=kind,
                balance_after=balance_after,
                meta=meta or {},
            )
        )
        await self.session.flush()
