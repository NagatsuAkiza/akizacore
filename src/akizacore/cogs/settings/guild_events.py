from typing import cast

import discord
import structlog
from discord.ext import commands

from akizacore.core.bot import AkizaBot
from akizacore.utils.converters import to_guild_info

log = structlog.get_logger()


class GuildEvents(commands.Cog):
    """Sinkronisasi guild ke database saat bot join/leave/start."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot
        self._synced = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._synced:
            return
        await self.bot.services.onboarding.sync_guilds([to_guild_info(g) for g in self.bot.guilds])
        self._synced = True
        log.info("guilds_synced", count=len(self.bot.guilds))

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.bot.services.onboarding.register_guild(to_guild_info(guild))
        log.info("guild_joined", guild_id=guild.id)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        await self.bot.services.onboarding.register_guild(to_guild_info(after))

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self.bot.services.onboarding.deactivate_guild(guild.id)
        log.info("guild_removed", guild_id=guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GuildEvents(cast(AkizaBot, bot)))
