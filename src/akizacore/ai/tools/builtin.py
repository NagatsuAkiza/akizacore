from typing import Literal

from pydantic import BaseModel, Field

from akizacore.ai.tools.base import Tool, ToolContext, clean_text
from akizacore.ai.tools.registry import ToolRegistry
from akizacore.services.economy import EconomyService
from akizacore.services.shop import ShopService
from akizacore.services.stats import StatsService


class NoArgs(BaseModel):
    """Tool tanpa argumen."""


class LeaderboardArgs(BaseModel):
    by: Literal["balance", "xp"] = Field("balance", description="Urutkan berdasarkan koin atau XP")
    limit: int = Field(5, ge=1, le=10, description="Jumlah baris yang ditampilkan (1-10)")


def build_default_registry(
    *, economy: EconomyService, shop: ShopService, stats: StatsService
) -> ToolRegistry:
    """Tool bawaan. Semuanya baca-saja dan memakai identitas dari ToolContext, bukan dari LLM."""

    async def get_balance(ctx: ToolContext, args: NoArgs) -> str:
        p = await economy.profile(ctx.server_id, ctx.user.id)
        return (
            f"Saldo: {p.balance} koin. Level {p.level} "
            f"(XP {p.xp_into_level}/{p.xp_needed} menuju level berikutnya)."
        )

    async def get_leaderboard(ctx: ToolContext, args: LeaderboardArgs) -> str:
        entries = await economy.leaderboard(ctx.server_id, by=args.by, limit=args.limit)
        if not entries:
            return "Belum ada data peringkat."
        lines = [
            f"{i}. {clean_text(e.username, 30)} - "
            + (f"{e.xp} XP (level {e.level})" if args.by == "xp" else f"{e.balance} koin")
            for i, e in enumerate(entries, start=1)
        ]
        title = "Peringkat XP:" if args.by == "xp" else "Peringkat koin:"
        return title + "\n" + "\n".join(lines)

    async def list_shop_items(ctx: ToolContext, args: NoArgs) -> str:
        items = await shop.list_items(ctx.server_id)
        if not items:
            return "Toko masih kosong."
        lines = []
        for item in items[:10]:
            stock = "" if item.stock is None else f", stok {item.stock}"
            desc = f" - {clean_text(item.description, 80)}" if item.description else ""
            lines.append(f"{clean_text(item.name, 50)}: {item.price} koin{stock}{desc}")
        return "Item toko:\n" + "\n".join(lines)

    async def get_server_stats(ctx: ToolContext, args: NoArgs) -> str:
        s = await stats.snapshot(ctx.server_id)
        return (
            f"Statistik server: {s.economy_accounts} akun ekonomi, "
            f"{s.coins_in_circulation} koin beredar, "
            f"{s.ai_requests_today} request AI hari ini ({s.ai_requests_7d} dalam 7 hari)."
        )

    return ToolRegistry(
        [
            Tool(
                "get_balance",
                "Lihat saldo koin, level, dan XP milik user yang sedang bertanya.",
                NoArgs,
                get_balance,
                feature="economy",
            ),
            Tool(
                "get_leaderboard",
                "Lihat peringkat teratas di server berdasarkan koin atau XP.",
                LeaderboardArgs,
                get_leaderboard,
                feature="economy",
            ),
            Tool(
                "list_shop_items",
                "Lihat daftar item yang dijual di toko server beserta harga dan stok.",
                NoArgs,
                list_shop_items,
                feature="economy",
            ),
            Tool(
                "get_server_stats",
                "Statistik ringkas server (akun ekonomi, koin beredar, pemakaian AI). Khusus admin.",
                NoArgs,
                get_server_stats,
                permission="admin",
            ),
        ]
    )
