from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import InventoryItem, ShopItem


class ShopRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_items(self, server_id: int) -> list[ShopItem]:
        stmt = (
            select(ShopItem)
            .where(ShopItem.server_id == server_id, ShopItem.is_active.is_(True))
            .order_by(ShopItem.price, ShopItem.name)
        )
        return list((await self.session.scalars(stmt)).all())

    async def find_by_name(
        self,
        server_id: int,
        name: str,
        *,
        active_only: bool = True,
        for_update: bool = False,
    ) -> ShopItem | None:
        stmt = select(ShopItem).where(
            ShopItem.server_id == server_id, func.lower(ShopItem.name) == name.strip().lower()
        )
        if active_only:
            stmt = stmt.where(ShopItem.is_active.is_(True))
        if for_update:
            stmt = stmt.with_for_update()
        stmt = stmt.execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        server_id: int,
        name: str,
        price: int,
        stock: int | None,
        description: str | None,
    ) -> ShopItem:
        item = ShopItem(
            server_id=server_id, name=name, price=price, stock=stock, description=description
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def search_names(self, server_id: int, prefix: str, limit: int) -> list[str]:
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = (
            select(ShopItem.name)
            .where(
                ShopItem.server_id == server_id,
                ShopItem.is_active.is_(True),
                ShopItem.name.ilike(f"{escaped}%", escape="\\"),
            )
            .order_by(ShopItem.name)
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def add_to_inventory(
        self, server_id: int, user_id: int, item_id: int, quantity: int
    ) -> None:
        stmt = insert(InventoryItem).values(
            server_id=server_id, user_id=user_id, item_id=item_id, quantity=quantity
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[InventoryItem.server_id, InventoryItem.user_id, InventoryItem.item_id],
            set_={"quantity": InventoryItem.quantity + quantity},
        )
        await self.session.execute(stmt)

    async def inventory(self, server_id: int, user_id: int) -> list[tuple[ShopItem, int]]:
        stmt = (
            select(ShopItem, InventoryItem.quantity)
            .join(InventoryItem, InventoryItem.item_id == ShopItem.id)
            .where(
                InventoryItem.server_id == server_id,
                InventoryItem.user_id == user_id,
                InventoryItem.quantity > 0,
            )
            .order_by(ShopItem.name)
        )
        return [(row[0], row[1]) for row in (await self.session.execute(stmt)).all()]
