from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from akizacore.core.bot import AkizaBot
from akizacore.schemas.settings import SettingsUpdate


class PersonaCog(commands.Cog):
    """Kepribadian AI per server (lapisan override persona)."""

    persona_group = app_commands.Group(
        name="persona",
        description="Kepribadian AI untuk server ini",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    @persona_group.command(name="view", description="Lihat persona AI server ini")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def view(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        data = await self.bot.services.settings.get(interaction.guild.id)
        text = data.ai_persona or "Belum ada persona khusus (memakai persona bawaan)."
        await interaction.response.send_message(text, ephemeral=True)

    @persona_group.command(name="set", description="Atur gaya bicara dan aturan khusus AI")
    @app_commands.describe(text="Contoh: Jawab santai, singkat, dan hindari topik politik")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_persona(
        self, interaction: discord.Interaction, text: app_commands.Range[str, 1, 500]
    ) -> None:
        assert interaction.guild is not None
        await self.bot.services.settings.update(
            interaction.guild.id, SettingsUpdate(ai_persona=text)
        )
        await interaction.response.send_message("Persona AI disimpan.", ephemeral=True)

    @persona_group.command(name="reset", description="Kembalikan ke persona bawaan")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reset(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await self.bot.services.settings.update(
            interaction.guild.id, SettingsUpdate(ai_persona=None)
        )
        await interaction.response.send_message("Persona AI direset.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PersonaCog(cast(AkizaBot, bot)))
