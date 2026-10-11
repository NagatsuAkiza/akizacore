import discord
import structlog
from discord import app_commands
from discord.ext import commands

from akizacore.config import Settings
from akizacore.core.exceptions import AkizaError
from akizacore.core.loader import load_cogs

log = structlog.get_logger()


class AkizaBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # privileged: aktifkan di Developer Portal (untuk chat via mention)
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.settings = settings
        self.tree.on_error = self.on_tree_error

    async def setup_hook(self) -> None:
        await load_cogs(self)
        if self.settings.dev_guild_id:
            guild = discord.Object(id=self.settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("commands_synced", scope="guild", guild_id=self.settings.dev_guild_id)
        else:
            await self.tree.sync()
            log.info("commands_synced", scope="global")

    async def on_ready(self) -> None:
        log.info("bot_ready", user=str(self.user), guilds=len(self.guilds))

    async def on_tree_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = getattr(error, "original", error)
        if isinstance(original, AkizaError):
            message = original.user_message
        else:
            log.exception("command_error", command=getattr(interaction.command, "name", None))
            message = "Terjadi kesalahan internal."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)