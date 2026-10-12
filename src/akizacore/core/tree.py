from typing import TYPE_CHECKING, cast

import discord
import structlog
from discord import app_commands

from akizacore.core.exceptions import AkizaError
from akizacore.utils.converters import to_guild_info, to_user_info

if TYPE_CHECKING:
    from akizacore.core.bot import AkizaBot

log = structlog.get_logger()


class AkizaTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Sebelum setiap command: pastikan user dan guild sudah terdaftar di database."""
        bot = cast("AkizaBot", interaction.client)
        guild = interaction.guild
        await bot.services.onboarding.ensure_context(
            to_user_info(interaction.user),
            to_guild_info(guild) if guild else None,
        )
        return True

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = getattr(error, "original", error)
        if isinstance(original, AkizaError):
            message = original.user_message
        elif isinstance(error, app_commands.MissingPermissions):
            message = "Kamu butuh izin Manage Server untuk command ini."
        elif isinstance(error, app_commands.CheckFailure):
            message = "Kamu tidak boleh memakai command ini."
        else:
            log.exception("command_error", command=getattr(interaction.command, "name", None))
            message = "Terjadi kesalahan internal."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
