from contextlib import suppress
from datetime import timedelta
from typing import cast

import discord
import structlog
from discord.ext import commands

from akizacore.core.bot import AkizaBot
from akizacore.schemas.moderation import AutomodView
from akizacore.services.automod import SpamTracker, find_blocked_links

log = structlog.get_logger()


class AutoModCog(commands.Cog):
    """Listener pesan: anti-spam dan anti-link. Moderator (Manage Messages) dikecualikan."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot
        self.tracker = SpamTracker()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        member = message.author
        if not isinstance(member, discord.Member) or member.guild_permissions.manage_messages:
            return
        if self.bot.is_owner_user(member.id):
            return
        try:
            cfg = await self.bot.services.moderation.get_automod(message.guild.id)
        except Exception:
            log.exception("automod_config_error", guild_id=message.guild.id)
            return
        if not (cfg.anti_spam or cfg.anti_link):
            return

        reason: str | None = None
        if cfg.anti_link:
            blocked = find_blocked_links(message.content, cfg.allowed_domains)
            if blocked:
                reason = "Link tidak diizinkan: " + ", ".join(blocked[:3])
        if cfg.anti_spam:
            is_spam = self.tracker.hit(
                message.guild.id,
                member.id,
                limit=cfg.spam_messages,
                window_s=cfg.spam_window_s,
            )
            if reason is None and is_spam:
                reason = "Spam pesan beruntun"
        if reason is None:
            return
        await self._enforce(message, member, cfg, reason)

    async def _enforce(
        self, message: discord.Message, member: discord.Member, cfg: AutomodView, reason: str
    ) -> None:
        assert message.guild is not None
        svc = self.bot.services.moderation
        try:
            await message.delete()
        except discord.HTTPException:
            log.warning("automod_delete_failed", guild_id=message.guild.id)

        notice = f"{member.mention} pesanmu dihapus: {reason}."
        try:
            await svc.log_action(
                server_id=message.guild.id,
                target_id=member.id,
                mod_id=None,
                action=f"automod:{cfg.action}",
                reason=reason,
            )
            if cfg.action == "warn":
                bot_id = self.bot.user.id if self.bot.user else 0
                result = await svc.warn(
                    server_id=message.guild.id,
                    user_id=member.id,
                    mod_id=bot_id,
                    reason=f"[automod] {reason}",
                )
                notice += f" Warn {result.total}/{svc.config.warn_timeout_at}."
                if result.escalate:
                    await self._timeout(member, svc.config.warn_timeout_minutes)
            elif cfg.action == "timeout":
                await self._timeout(member, cfg.timeout_minutes)
        except Exception:
            log.exception("automod_enforce_error", guild_id=message.guild.id)

        with suppress(discord.HTTPException):
            await message.channel.send(
                notice, delete_after=8, allowed_mentions=discord.AllowedMentions(users=[member])
            )

    @staticmethod
    async def _timeout(member: discord.Member, minutes: int) -> None:
        try:
            await member.timeout(timedelta(minutes=minutes), reason="Automod")
        except discord.HTTPException:
            log.warning("automod_timeout_failed", member_id=member.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoModCog(cast(AkizaBot, bot)))
