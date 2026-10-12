from pydantic import BaseModel, ConfigDict


class ProfileView(BaseModel):
    balance: int
    xp: int
    level: int
    xp_into_level: int
    xp_needed: int


class DailyResult(BaseModel):
    amount: int
    balance: int
    xp_gained: int
    level: int
    leveled_up: bool
    bonus_coins: int = 0


class WorkResult(BaseModel):
    job: str
    amount: int
    balance: int
    xp_gained: int
    level: int
    leveled_up: bool
    bonus_coins: int = 0


class XpResult(BaseModel):
    xp_gained: int
    level: int
    leveled_up: bool
    bonus_coins: int = 0


class TransferResult(BaseModel):
    amount: int
    sender_balance: int
    receiver_balance: int


class LeaderboardEntry(BaseModel):
    user_id: int
    username: str
    balance: int
    xp: int
    level: int


class ShopItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    price: int
    stock: int | None = None
    is_active: bool = True


class InventoryEntry(BaseModel):
    item_id: int
    name: str
    quantity: int


class PurchaseResult(BaseModel):
    item_name: str
    quantity: int
    total_cost: int
    balance: int
