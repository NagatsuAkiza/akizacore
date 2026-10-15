from typing import cast

import discord
import structlog
from discord.ext import commands, tasks

from akizacore.core.bot import AkizaBot
from akizacore.services.quota_alert import QuotaAlerter

log = structlog.get_logger()


class AIMaintenance(commands.Cog):
    """Tugas berkala AI: pembersihan data kedaluwarsa dan peringatan kuota ke owner."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot
        self.alerter = QuotaAlerter()
        self.purge_loop.start()
        self.quota_loop.start()

    async def cog_unload(self) -> None:
        self.purge_loop.cancel()
        self.quota_loop.cancel()

    @tasks.loop(hours=6)
    async def purge_loop(self) -> None:
        ai = self.bot.services.ai
        if ai is not None:
            try:
                messages, conversations = await ai.purge_expired()
            except Exception:
                log.exception("purge_failed")
            else:
                log.info("history_purged", messages=messages, conversations=conversations)
        try:
            usage_rows = await self.bot.services.usage.purge_expired()
        except Exception:
            log.exception("usage_purge_failed")
        else:
            log.info("usage_purged", rows=usage_rows)

    @purge_loop.before_loop
    async def _before_purge(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=10)
    async def quota_loop(self) -> None:
        """DM owner saat kuota AI global mencapai 80% dan 100% (sekali per ambang per hari)."""
        owner_id = self.bot.settings.owner_user_id
        if owner_id is None:
            return
        try:
            used, limit, today = await self.bot.services.usage.global_quota_status()
        except Exception:
            log.exception("quota_check_failed")
            return
        level = self.alerter.next_alert(used, limit, today)
        if level is None:
            return
        log.warning("ai_quota_alert", level=level, used=used, limit=limit)
        advice = (
            "Permintaan AI baru akan ditolak sampai besok."
            if level >= 100
            else "Pantau lewat /usage, atau naikkan AI_DAILY_GLOBAL_LIMIT bila perlu."
        )
        try:
            owner = await self.bot.fetch_user(owner_id)
            await owner.send(
                f"Kuota AI global hari ini {level}% terpakai ({used}/{limit}). {advice}"
            )
        except discord.HTTPException:
            log.warning("ai_quota_alert_dm_failed", owner_id=owner_id)

    @quota_loop.before_loop
    async def _before_quota(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIMaintenance(cast(AkizaBot, bot)))
