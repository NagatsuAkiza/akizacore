from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from akizacore.database.base import Base


class ShopItem(Base):
    """Item toko per server. Tidak dihapus permanen (is_active=False) agar inventory tetap valid."""

    __tablename__ = "shop_items"
    __table_args__ = (UniqueConstraint("server_id", "name", name="uq_shop_item_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("servers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(200), default=None)
    price: Mapped[int] = mapped_column(BigInteger)
    stock: Mapped[int | None] = mapped_column(Integer, default=None)  # None = tak terbatas
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InventoryItem(Base):
    __tablename__ = "inventory"

    server_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("shop_items.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
