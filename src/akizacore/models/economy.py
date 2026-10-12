from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from akizacore.database.base import Base, TimestampMixin


class EconomyAccount(TimestampMixin, Base):
    """Saldo, XP, dan level per (server, user)."""

    __tablename__ = "economy"

    server_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    balance: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    xp: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    level: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    last_daily: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Transaction(Base):
    """Ledger append-only: setiap perubahan saldo harus punya satu baris di sini."""

    __tablename__ = "transactions"
    __table_args__ = (Index("ix_transactions_scope", "server_id", "user_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("servers.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    amount: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(32))
    balance_after: Mapped[int] = mapped_column(BigInteger)
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
