from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from akizacore.core.bot import AkizaBot


class EconomyBasic(commands.Cog):
    """Command ekonomi minimal. Diperluas di Fase 4 (daily, leaderboard, shop, ...)."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    @app_commands.command(name="balance", description="Lihat saldo koinmu di server ini")
    @app_commands.guild_only()
    async def balance(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        amount = await self.bot.services.economy.balance(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(f"Saldo kamu: **{amount}** koin.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EconomyBasic(cast(AkizaBot, bot)))
