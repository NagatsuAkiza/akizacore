from typing import cast

import structlog
from discord.ext import commands, tasks

from akizacore.core.bot import AkizaBot

log = structlog.get_logger()


class AIMaintenance(commands.Cog):
    """Pembersihan berkala riwayat percakapan yang melewati masa retensi."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot
        self.purge_loop.start()

    async def cog_unload(self) -> None:
        self.purge_loop.cancel()

    @tasks.loop(hours=6)
    async def purge_loop(self) -> None:
        ai = self.bot.services.ai
        if ai is None:
            return
        try:
            messages, conversations = await ai.purge_expired()
        except Exception:
            log.exception("purge_failed")
            return
        log.info("history_purged", messages=messages, conversations=conversations)

    @purge_loop.before_loop
    async def _before_purge(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIMaintenance(cast(AkizaBot, bot)))
