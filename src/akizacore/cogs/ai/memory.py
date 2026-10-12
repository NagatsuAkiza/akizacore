from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from akizacore.core.bot import AkizaBot
from akizacore.core.exceptions import AkizaError


class MemoryCog(commands.Cog):
    """Command untuk mengelola memory AI yang disimpan user secara eksplisit."""

    memory_group = app_commands.Group(
        name="memory",
        description="Kelola memory AI kamu",
        guild_only=True,
    )

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    @memory_group.command(name="save", description="Simpan memory AI untuk server ini")
    @app_commands.describe(content="Hal yang ingin diingat AI (maksimal 500 karakter)")
    async def save(
        self, interaction: discord.Interaction, content: app_commands.Range[str, 1, 500]
    ) -> None:
        assert interaction.guild is not None
        try:
            await self.bot.services.memory.save(interaction.guild.id, interaction.user.id, content)
        except AkizaError as exc:
            await interaction.response.send_message(exc.user_message, ephemeral=True)
            return
        await interaction.response.send_message("Memory berhasil disimpan.", ephemeral=True)

    @memory_group.command(name="list", description="Lihat memory AI yang tersimpan")
    async def list(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        try:
            memories = await self.bot.services.memory.list(
                interaction.guild.id, interaction.user.id
            )
        except AkizaError as exc:
            await interaction.response.send_message(exc.user_message, ephemeral=True)
            return
        if not memories:
            text = "Belum ada memory tersimpan."
        else:
            text = "\n".join(f"{memory.id}. {memory.content}" for memory in memories)
            text = text[:1990]
        await interaction.response.send_message(text, ephemeral=True)

    @memory_group.command(name="delete", description="Hapus satu memory AI")
    @app_commands.describe(memory_id="ID memory yang ingin dihapus")
    async def delete(self, interaction: discord.Interaction, memory_id: int) -> None:
        assert interaction.guild is not None
        try:
            await self.bot.services.memory.delete(
                interaction.guild.id, interaction.user.id, memory_id
            )
        except AkizaError as exc:
            await interaction.response.send_message(exc.user_message, ephemeral=True)
            return
        await interaction.response.send_message("Memory berhasil dihapus.", ephemeral=True)

    @memory_group.command(name="clear", description="Hapus semua memory AI kamu")
    async def clear(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        try:
            count = await self.bot.services.memory.clear(interaction.guild.id, interaction.user.id)
        except AkizaError as exc:
            await interaction.response.send_message(exc.user_message, ephemeral=True)
            return
        await interaction.response.send_message(f"{count} memory berhasil dihapus.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MemoryCog(cast(AkizaBot, bot)))
