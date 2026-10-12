from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from akizacore.core.bot import AkizaBot

FEATURE_LABELS = {
    "ask": "AI Assistant",
    "translate": "AI Assistant",
    "forget": "AI Assistant",
    "balance": "Economy",
    "daily": "Economy",
    "work": "Economy",
    "leaderboard": "Economy",
    "transfer": "Economy",
    "shop": "Economy",
    "buy": "Economy",
    "inventory": "Economy",
    "shopadmin": "Economy",
    "warn": "Moderation",
    "warnings": "Moderation",
    "clearwarns": "Moderation",
    "kick": "Moderation",
    "ban": "Moderation",
    "timeout": "Moderation",
    "untimeout": "Moderation",
    "purge": "Moderation",
    "modlog": "Moderation",
    "automod": "Moderation",
    "setup": "Server Settings",
    "persona": "Server Settings",
    "ping": "Utility",
    "userinfo": "Utility",
    "serverinfo": "Utility",
    "help": "Utility",
}

FEATURE_ORDER = ["AI Assistant", "Economy", "Moderation", "Server Settings", "Utility"]


class HelpCog(commands.Cog):
    """Menampilkan command slash yang sedang terdaftar, dikelompokkan berdasarkan fitur."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    @staticmethod
    def _feature(command: app_commands.Command | app_commands.Group) -> str:
        root_name = command.qualified_name.split(" ", maxsplit=1)[0]
        return FEATURE_LABELS.get(root_name, "Lainnya")

    @app_commands.command(name="help", description="Lihat daftar command yang tersedia")
    async def help(self, interaction: discord.Interaction) -> None:
        grouped: dict[str, list[str]] = {feature: [] for feature in FEATURE_ORDER}
        grouped["Lainnya"] = []
        for command in self.bot.tree.walk_commands():
            if isinstance(command, app_commands.Group):
                continue
            feature = self._feature(command)
            grouped.setdefault(feature, []).append(
                f"`/{command.qualified_name}` - {command.description or 'Tanpa deskripsi'}"
            )

        embed = discord.Embed(
            title="Command AkizaCore",
            description="Pilih command sesuai fitur yang ingin kamu gunakan.",
            color=discord.Color.blurple(),
        )
        for feature in [*FEATURE_ORDER, "Lainnya"]:
            lines = sorted(grouped[feature])
            if lines:
                embed.add_field(name=feature, value="\n".join(lines), inline=False)
        if not any(grouped.values()):
            embed.description = "Belum ada command yang tersedia."
        embed.set_footer(text="Gunakan /help kapan saja untuk melihat daftar terbaru.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(cast(AkizaBot, bot)))
