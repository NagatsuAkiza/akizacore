from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from akizacore.core.bot import AkizaBot


class HelpCog(commands.Cog):
    """Menampilkan command slash yang sedang terdaftar di bot."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="Lihat daftar command yang tersedia")
    async def help(self, interaction: discord.Interaction) -> None:
        commands_list = sorted(self.bot.tree.walk_commands(), key=lambda command: command.name)
        lines = [
            f"`/{command.qualified_name}` - {command.description or 'Tanpa deskripsi'}"
            for command in commands_list
        ]
        embed = discord.Embed(
            title="Command AkizaCore",
            description="\n".join(lines) or "Belum ada command yang tersedia.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Gunakan /help kapan saja untuk melihat daftar terbaru.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(cast(AkizaBot, bot)))
