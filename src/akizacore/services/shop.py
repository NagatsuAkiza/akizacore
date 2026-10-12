from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.core.exceptions import NotFound, ValidationFailed
from akizacore.database.repositories import ShopRepository
from akizacore.database.session import session_scope
from akizacore.schemas.economy import InventoryEntry, PurchaseResult, ShopItemRead
from akizacore.services.economy import EconomyService

MAX_PRICE = 1_000_000
MAX_STOCK = 100_000
MAX_QUANTITY = 99


class ShopService:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, economy: EconomyService
    ) -> None:
        self._sf = session_factory
        self._economy = economy

    async def list_items(self, server_id: int) -> list[ShopItemRead]:
        async with session_scope(self._sf) as session:
            items = await ShopRepository(session).list_items(server_id)
            return [ShopItemRead.model_validate(item) for item in items]

    async def search_names(self, server_id: int, prefix: str, limit: int = 25) -> list[str]:
        async with session_scope(self._sf) as session:
            return await ShopRepository(session).search_names(server_id, prefix, limit)

    async def add_item(
        self,
        server_id: int,
        name: str,
        price: int,
        stock: int | None = None,
        description: str | None = None,
    ) -> ShopItemRead:
        name = name.strip()
        description = description.strip() if description else None
        if not 1 <= len(name) <= 50:
            raise ValidationFailed("Nama item harus 1-50 karakter.")
        if not 1 <= price <= MAX_PRICE:
            raise ValidationFailed(f"Harga harus antara 1 dan {MAX_PRICE}.")
        if stock is not None and not 0 <= stock <= MAX_STOCK:
            raise ValidationFailed(
                f"Stok harus antara 0 dan {MAX_STOCK} (kosongkan untuk tak terbatas)."
            )
        if description is not None and len(description) > 200:
            raise ValidationFailed("Deskripsi maksimal 200 karakter.")

        async with session_scope(self._sf) as session:
            repo = ShopRepository(session)
            existing = await repo.find_by_name(server_id, name, active_only=False)
            if existing is not None and existing.is_active:
                raise ValidationFailed("Item dengan nama itu sudah ada.")
            if existing is not None:  # item lama yang pernah dihapus: aktifkan kembali
                existing.price = price
                existing.stock = stock
                existing.description = description
                existing.is_active = True
                item = existing
            else:
                item = await repo.create(server_id, name, price, stock, description)
            return ShopItemRead.model_validate(item)

    async def remove_item(self, server_id: int, name: str) -> None:
        async with session_scope(self._sf) as session:
            item = await ShopRepository(session).find_by_name(server_id, name)
            if item is None:
                raise NotFound("Item tidak ditemukan.")
            item.is_active = False  # soft delete: inventory pemain tetap utuh

    async def buy(
        self, server_id: int, user_id: int, name: str, quantity: int = 1
    ) -> PurchaseResult:
        if not 1 <= quantity <= MAX_QUANTITY:
            raise ValidationFailed(f"Jumlah beli harus antara 1 dan {MAX_QUANTITY}.")
        async with session_scope(self._sf) as session:
            repo = ShopRepository(session)
            item = await repo.find_by_name(server_id, name, for_update=True)
            if item is None:
                raise NotFound("Item tidak ditemukan.")
            if item.stock is not None and item.stock < quantity:
                raise ValidationFailed(f"Stok tidak cukup (sisa {item.stock}).")

            total = item.price * quantity
            balance = await self._economy.apply_in_session(
                session,
                server_id,
                user_id,
                -total,
                "shop_buy",
                {"item_id": item.id, "name": item.name, "qty": quantity},
            )
            if item.stock is not None:
                item.stock -= quantity
            await repo.add_to_inventory(server_id, user_id, item.id, quantity)
            return PurchaseResult(
                item_name=item.name, quantity=quantity, total_cost=total, balance=balance
            )

    async def inventory(self, server_id: int, user_id: int) -> list[InventoryEntry]:
        async with session_scope(self._sf) as session:
            rows = await ShopRepository(session).inventory(server_id, user_id)
            return [
                InventoryEntry(item_id=item.id, name=item.name, quantity=qty) for item, qty in rows
            ]
