from typing import Literal

from pydantic import BaseModel, Field

from akizacore.ai.tools.base import ModerationGateway, Tool, ToolContext, clean_text
from akizacore.ai.tools.registry import ToolRegistry
from akizacore.services.economy import EconomyService
from akizacore.services.shop import ShopService
from akizacore.services.stats import StatsService


class NoArgs(BaseModel):
    """Tool tanpa argumen."""


class LeaderboardArgs(BaseModel):
    by: Literal["balance", "xp"] = Field("balance", description="Urutkan berdasarkan koin atau XP")
    limit: int = Field(5, ge=1, le=10, description="Jumlah baris yang ditampilkan (1-10)")


class ModerationTargetArgs(BaseModel):
    user_id: int = Field(..., gt=0, description="ID Discord member target")


class ModerationReasonArgs(ModerationTargetArgs):
    reason: str = Field("Tanpa alasan", min_length=1, max_length=300)


class ModlogArgs(BaseModel):
    user_id: int | None = Field(None, gt=0, description="Filter ID member, opsional")


class DestructiveModerationArgs(BaseModel):
    action: Literal["kick", "ban", "timeout", "untimeout", "purge", "add_role", "remove_role"]
    user_id: int | None = Field(None, gt=0, description="ID member target")
    reason: str = Field("Tanpa alasan", min_length=1, max_length=300)
    minutes: int | None = Field(None, ge=1, le=40320, description="Durasi timeout dalam menit")
    amount: int | None = Field(None, ge=1, le=100, description="Jumlah pesan yang dihapus")
    role_id: int | None = Field(None, gt=0, description="ID role yang dikelola")


def build_default_registry(
    *, economy: EconomyService, shop: ShopService, stats: StatsService
) -> ToolRegistry:
    """Build built-in tools using identity and authorization from ToolContext."""

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

    async def moderation_gateway(ctx: ToolContext) -> "ModerationGateway":
        if ctx.moderation is None:
            raise RuntimeError("moderation gateway tidak tersedia")
        return ctx.moderation

    async def warn_member(ctx: ToolContext, args: ModerationReasonArgs) -> str:
        return await (await moderation_gateway(ctx)).warn(args.user_id, args.reason)

    async def list_warnings(ctx: ToolContext, args: ModerationTargetArgs) -> str:
        return await (await moderation_gateway(ctx)).warnings(args.user_id)

    async def clear_member_warnings(ctx: ToolContext, args: ModerationTargetArgs) -> str:
        return await (await moderation_gateway(ctx)).clear_warnings(args.user_id)

    async def show_modlog(ctx: ToolContext, args: ModlogArgs) -> str:
        return await (await moderation_gateway(ctx)).modlog(args.user_id)

    async def request_destructive_moderation(
        ctx: ToolContext, args: DestructiveModerationArgs
    ) -> str:
        return await (await moderation_gateway(ctx)).request_destructive(
            action=args.action,
            target_id=args.user_id,
            reason=args.reason,
            minutes=args.minutes,
            amount=args.amount,
            role_id=args.role_id,
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
            Tool(
                "moderation_warn",
                "Beri warning kepada member. Memerlukan izin moderasi.",
                ModerationReasonArgs,
                warn_member,
                permission="admin",
                feature="moderation",
                side_effect="write",
            ),
            Tool(
                "moderation_warnings",
                "Lihat warning aktif milik member.",
                ModerationTargetArgs,
                list_warnings,
                permission="admin",
                feature="moderation",
            ),
            Tool(
                "moderation_clear_warnings",
                "Hapus seluruh warning aktif milik member.",
                ModerationTargetArgs,
                clear_member_warnings,
                permission="admin",
                feature="moderation",
                side_effect="write",
            ),
            Tool(
                "moderation_modlog",
                "Lihat catatan moderasi terbaru, opsional berdasarkan member.",
                ModlogArgs,
                show_modlog,
                permission="admin",
                feature="moderation",
            ),
            Tool(
                "moderation_request",
                (
                    "Ajukan kick, ban, timeout, untimeout, purge, atau add/remove role. "
                    "Tool ini tidak langsung menjalankan aksi: user wajib mengonfirmasi "
                    "token melalui /confirm."
                ),
                DestructiveModerationArgs,
                request_destructive_moderation,
                permission="admin",
                feature="moderation",
                side_effect="write",
            ),
        ]
    )
