from typing import Literal, cast

import discord
from discord import app_commands
from discord.ext import commands

from akizacore.core.bot import AkizaBot
from akizacore.core.exceptions import PermissionDenied
from akizacore.schemas.ai_usage import UsageTotals


def _n(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _latency(totals: UsageTotals) -> str:
    if totals.avg_latency_ms is None:
        return "-"
    return f"{_n(totals.avg_latency_ms)} ms (p95 {_n(totals.p95_latency_ms or 0)} ms)"


class UsageCog(commands.Cog):
    """Tracking pemakaian AI. Cog tipis: semua hitungan ada di AIUsageService."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    @app_commands.command(name="usage", description="Lihat pemakaian AI: milikmu atau server")
    @app_commands.describe(
        scope="me = pemakaianmu, server = ringkasan server (butuh Manage Server)",
        days="Rentang hari untuk ringkasan server (1 sampai 30)",
    )
    @app_commands.guild_only()
    async def usage(
        self,
        interaction: discord.Interaction,
        scope: Literal["me", "server"] = "me",
        days: app_commands.Range[int, 1, 30] = 7,
    ) -> None:
        if scope == "server":
            await self._server(interaction, days)
        else:
            await self._me(interaction)

    async def _me(self, interaction: discord.Interaction) -> None:
        data = await self.bot.services.usage.my_usage(interaction.user.id)
        week = data.last_7_days
        embed = discord.Embed(title="Pemakaian AI-mu", color=discord.Color.blurple())
        embed.add_field(
            name="Hari ini",
            value=(
                f"{data.used_today}/{data.user_limit} pertanyaan "
                f"(sisa {max(0, data.user_limit - data.used_today)})"
            ),
        )
        embed.add_field(
            name="Kuota bot (semua user)", value=f"{data.global_used_today}/{data.global_limit}"
        )
        embed.add_field(name="Token hari ini", value=_n(data.tokens_today))
        embed.add_field(name="Koin terpakai hari ini", value=_n(data.coins_today))
        embed.add_field(
            name="7 hari terakhir",
            value=(
                f"{_n(week.requests)} pertanyaan, "
                f"{_n(week.prompt_tokens + week.completion_tokens)} token, "
                f"{_n(week.errors)} gagal, {_n(week.rejected)} ditolak (kuota), "
                f"{_n(week.rule_hits)} dijawab tanpa AI"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _server(self, interaction: discord.Interaction, days: int) -> None:
        assert interaction.guild is not None
        if not (
            self.bot.is_owner_user(interaction.user.id) or interaction.permissions.manage_guild
        ):
            raise PermissionDenied("Ringkasan server hanya untuk admin (Manage Server).")

        report = await self.bot.services.usage.server_report(interaction.guild.id, days=days)
        totals = report.totals
        embed = discord.Embed(
            title=f"Pemakaian AI {interaction.guild.name} ({report.days} hari)",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Pertanyaan", value=_n(totals.requests))
        embed.add_field(name="Dijawab tanpa AI", value=_n(totals.rule_hits))
        embed.add_field(name="Gagal", value=_n(totals.errors))
        embed.add_field(name="Ditolak (kuota)", value=_n(totals.rejected))
        embed.add_field(
            name="Token",
            value=f"{_n(totals.prompt_tokens)} prompt / {_n(totals.completion_tokens)} jawaban",
        )
        embed.add_field(name="Koin terpakai", value=_n(totals.coins))
        embed.add_field(name="Latensi rata-rata", value=_latency(totals))
        if report.top_users:
            lines = [
                f"{i}. <@{u.user_id}> - {_n(u.requests)} ({_n(u.tokens)} token)"
                for i, u in enumerate(report.top_users, start=1)
            ]
            embed.add_field(name="Pemakai teratas", value="\n".join(lines), inline=False)
        if report.by_model:
            lines = [f"{m.name}: {_n(m.requests)}" for m in report.by_model[:3]]
            embed.add_field(name="Model", value="\n".join(lines))
        if report.tools:
            lines = [f"{t.name}: {_n(t.requests)}" for t in report.tools[:5]]
            embed.add_field(name="Tool", value="\n".join(lines))
        if report.recent_errors:
            lines = [
                f"{discord.utils.format_dt(e.created_at, 'R')} {e.kind} {e.error_code or '-'}"
                for e in report.recent_errors[:3]
            ]
            embed.add_field(name="Error terakhir", value="\n".join(lines), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UsageCog(cast(AkizaBot, bot)))
